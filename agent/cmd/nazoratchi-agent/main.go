// nazoratchi-agent — kuzatiladigan serverda ishlaydigan yagona statik binar (TZ 7).
//
//	nazoratchi-agent run [--config yo'l]            # standart buyruq
//	nazoratchi-agent enroll --core URL --token enr_...  # bir martalik token -> doimiy token
//	nazoratchi-agent check-config [--config yo'l]
//	nazoratchi-agent collect                         # bir martalik yig'ish (diagnostika), JSON
//	nazoratchi-agent beat <job> [--dir /var/lib/nazoratchi/heartbeats]  # cron oxirida: heartbeat yozadi
//	nazoratchi-agent uninstall [--config yo'l] [--purge] [--yes]   # agentni o'chirish (FR-AGT-013)
//	nazoratchi-agent version
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"nazoratchi/agent/internal/agent"
	"nazoratchi/agent/internal/config"
	"nazoratchi/agent/internal/facts"
	"nazoratchi/agent/internal/metric"
	"nazoratchi/agent/internal/sender"
)

// version yig'ishda `-ldflags "-X main.version=1.0.0"` bilan o'rnatiladi.
var version = "dev"

func main() {
	args := os.Args[1:]
	cmd := "run"
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		cmd, args = args[0], args[1:]
	}
	var err error
	switch cmd {
	case "run":
		err = cmdRun(args)
	case "enroll":
		err = cmdEnroll(args, os.Stdout)
	case "check-config":
		err = cmdCheckConfig(args, os.Stdout)
	case "beat":
		err = cmdBeat(args, os.Stdout)
	case "uninstall":
		err = cmdUninstall(args, os.Stdout)
	case "collect":
		err = cmdCollect(os.Stdout)
	case "version":
		fmt.Printf("nazoratchi-agent %s (%s, %s/%s)\n", version, runtime.Version(), runtime.GOOS, runtime.GOARCH)
	default:
		err = fmt.Errorf("noma'lum buyruq %q (run, enroll, check-config, collect, beat, uninstall, version)", cmd)
	}
	if err != nil {
		var ee *exitError
		if errors.As(err, &ee) {
			if ee.Msg != "" {
				fmt.Fprintln(os.Stderr, ee.Msg)
			}
			os.Exit(ee.Code)
		}
		fmt.Fprintln(os.Stderr, "xato:", err)
		os.Exit(1)
	}
}

func newLogger(level string) *slog.Logger {
	var l slog.Level
	_ = l.UnmarshalText([]byte(level))
	h := slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: l})
	return slog.New(h).With("component", "agent")
}

func configFlag(fs *flag.FlagSet) *string {
	return fs.String("config", config.DefaultPath, "sozlama fayli")
}

func cmdCheckConfig(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("check-config", flag.ContinueOnError)
	path := configFlag(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	if _, err := config.Load(*path); err != nil {
		return err
	}
	fmt.Fprintln(out, "sozlama yaroqli:", *path)
	return nil
}

// cmdRun: SIGTERM/SIGINT -> toza to'xtash; SIGHUP -> sozlamani qayta o'qib qayta ishga tushirish.
func cmdRun(args []string) error {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	path := configFlag(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	hup := make(chan os.Signal, 1)
	signal.Notify(hup, syscall.SIGHUP)

	for {
		cfg, err := config.Load(*path)
		if err != nil {
			return err
		}
		log := newLogger(cfg.Log.Level)
		token, err := loadToken(cfg.Core.TokenFile, log)
		if err != nil {
			return err
		}
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		go func() {
			done <- agent.Run(ctx, agent.Options{Cfg: cfg, Token: token, Version: version, Log: log})
		}()
		select {
		case err := <-done:
			cancel()
			return err
		case <-stop:
			cancel()
			return <-done
		case <-hup:
			log.Info("SIGHUP: sozlama qayta o'qilmoqda")
			if _, err := config.Load(*path); err != nil {
				log.Error("yangi sozlama yaroqsiz, eskisi bilan davom etiladi", "error", err)
				select { // eski ishlayotgan nusxani to'xtatmaymiz
				case err := <-done:
					cancel()
					return err
				case <-stop:
					cancel()
					return <-done
				}
			}
			cancel()
			<-done
		}
	}
}

// loadToken tokenni fayldan o'qiydi; fayl boshqalarga ochiq bo'lsa ogohlantiradi (TZ 7.6: rejim 0600).
func loadToken(path string, log *slog.Logger) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("token fayli topilmadi (%s); avval `nazoratchi-agent enroll` ni ishga tushiring: %w", path, err)
	}
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o077 != 0 {
		log.Warn("token fayli boshqalarga ochiq; rejimni 0600 qiling", "path", path, "mode", info.Mode().Perm().String())
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	token := strings.TrimSpace(string(data))
	if token == "" {
		return "", fmt.Errorf("token fayli bo'sh: %s", path)
	}
	return token, nil
}

func cmdEnroll(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("enroll", flag.ContinueOnError)
	path := configFlag(fs)
	core := fs.String("core", "", "core manzili (standart: sozlamadan)")
	token := fs.String("token", os.Getenv("NAZORATCHI_ENROLL_TOKEN"), "bir martalik enroll token (yoki NAZORATCHI_ENROLL_TOKEN)")
	tokenFile := fs.String("token-file", "", "doimiy token yoziladigan fayl (standart: sozlamadan)")
	caFile := fs.String("ca-file", "", "o'zi imzolagan CA (ixtiyoriy)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *token == "" {
		return errors.New("enroll token kerak: --token yoki NAZORATCHI_ENROLL_TOKEN")
	}

	cfg := config.Default()
	if _, err := os.Stat(*path); err == nil {
		loaded, err := config.Load(*path)
		if err != nil {
			return err
		}
		cfg = loaded
	}
	coreURL, ca, dest := cfg.Core.URL, cfg.Core.CAFile, cfg.Core.TokenFile
	if *core != "" {
		coreURL = *core
	}
	if *caFile != "" {
		ca = *caFile
	}
	if *tokenFile != "" {
		dest = *tokenFile
	}
	if err := config.ValidateCoreURL(coreURL); err != nil {
		return fmt.Errorf("core manzili: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	res, err := sender.Enroll(ctx, coreURL, ca, 15*time.Second, *token, version, facts.Default(cfg.Host.Name).Collect())
	if err != nil {
		return fmt.Errorf("enroll muvaffaqiyatsiz: %w", err)
	}
	if err := writeTokenFile(dest, res.AgentToken); err != nil {
		return fmt.Errorf("doimiy token yozilmadi: %w", err)
	}
	fmt.Fprintf(out, "Nazoratchi'ga ulandi: host %s (token: %s, rejim 0600)\n", res.HostID, dest)
	return nil
}

// writeTokenFile tokenni atomik, 0600 rejimda yozadi (avval tmp, keyin rename): yarim yozilgan token qolmaydi.
func writeTokenFile(path, token string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return err
	}
	tmp := path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.WriteString(token + "\n"); err != nil {
		f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return os.Rename(tmp, path)
}

// cmdCollect ikki marta yig'adi (CPU/tarmoq tezligi ikki o'lchov farqi) va ikkinchisini chop etadi.
func cmdCollect(out io.Writer) error {
	jobs, _ := agent.BuildJobs(config.Default(), "/proc")
	ctx := context.Background()
	var last []metric.Sample
	for round := 0; round < 2; round++ {
		if round > 0 {
			time.Sleep(time.Second)
		}
		last = last[:0]
		for _, j := range jobs {
			s, err := j.C.Collect(ctx, time.Now())
			if err != nil {
				fmt.Fprintf(os.Stderr, "ogohlantirish: %s: %v\n", j.C.Name(), err)
			}
			last = append(last, s...)
		}
	}
	enc := json.NewEncoder(out)
	enc.SetIndent("", "  ")
	return enc.Encode(map[string]any{"facts": facts.Default("").Collect(), "samples": last})
}
