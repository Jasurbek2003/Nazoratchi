package main

import (
	"flag"
	"fmt"
	"io"
	"log/slog"
	"runtime"
	"time"

	"nazoratchi/agent/internal/config"
	"nazoratchi/agent/internal/facts"
	"nazoratchi/agent/internal/sender"
	"nazoratchi/agent/internal/update"
)

// newUpdater: ochiq kalit bo'lmasa ham qaytaradi (Stage "kalitsiz" deb rad etadi va sabab loglanadi).
func newUpdater(cfg *config.Config, log *slog.Logger) *update.Updater {
	hc, err := sender.NewHTTPClient(cfg.Core.CAFile, 0)
	if err != nil {
		log.Error("yangilanish uchun HTTP klient yaratilmadi", "error", err)
		return nil
	}
	u, err := update.New(update.Config{
		CoreURL: cfg.Core.URL, PubKey: releasePubKey, Arch: runtime.GOARCH, Current: version, HTTP: hc,
	})
	if err != nil {
		log.Error("yangilanish o'chirildi: ochiq kalit yaroqsiz", "error", err)
		return nil
	}
	if !u.Enabled() {
		log.Info("o'z-o'zini yangilash o'chiq: agent minisign ochiq kalitisiz yig'ilgan")
	}
	return u
}

// cmdApplyUpdate systemd `ExecStartPre=+` da root sifatida ishlaydi (TZ 7.7.3). Chiqish kodi 0: hammasi joyida
// yoki yangilanish rad etildi (agent eski binar bilan ishga tushadi). 1: kutilmagan xato; unit ichidagi
// skript shunda kutilayotgan yangilanishni qo'lda qaytaradi (yangi binar umuman ishlamasa ham).
func cmdApplyUpdate(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("apply-update", flag.ContinueOnError)
	bin := fs.String("bin", "/usr/local/bin/nazoratchi-agent", "o'rnatilgan binar")
	stage := fs.String("stage", update.DefaultStageDir, "agent yuklagan yangilanish papkasi")
	state := fs.String("state", update.DefaultStateDir, "root holat papkasi")
	if err := fs.Parse(args); err != nil {
		return err
	}
	outcome, err := update.Apply(update.ApplyConfig{
		Bin: *bin, StageDir: *stage, StateDir: *state, PubKey: releasePubKey, Arch: runtime.GOARCH, Current: version,
		Now:  time.Now,
		Logf: func(f string, a ...any) { fmt.Fprintf(out, "apply-update: "+f+"\n", a...) },
	})
	if err != nil {
		fmt.Fprintf(out, "apply-update: %s: %v\n", outcome, err)
		if outcome == update.OutcomeRejected {
			return nil // rad etilgan yangilanish agentning eski binar bilan ishlashiga xalaqit bermaydi
		}
		return &exitError{Code: 1}
	}
	fmt.Fprintf(out, "apply-update: %s\n", outcome)
	return nil
}

// enrollFacts: birinchi paket (enroll) faktlari, build vaqti bilan.
func enrollFacts(hostName string) map[string]any {
	src := facts.Default(hostName)
	src.BuildTime = buildTime
	return src.Collect()
}
