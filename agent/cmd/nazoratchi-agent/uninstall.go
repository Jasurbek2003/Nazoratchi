package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"nazoratchi/agent/internal/config"
	"nazoratchi/agent/internal/sender"
)

// O'chirishda tegiladigan YAGONA yo'llar (mantiqiy, ildizsiz). Boshqa hech narsa o'chirilmaydi.
const (
	unitPath       = "/etc/systemd/system/nazoratchi-agent.service"
	configDir      = "/etc/nazoratchi"
	stateDir       = "/var/lib/nazoratchi"
	updateStateDir = "/var/lib/nazoratchi-update" // rollback holati (root)
	prestartDir    = "/usr/local/lib/nazoratchi"  // ExecStartPre o'rovi
	binDir         = "/usr/local/bin/"
	serviceName    = "nazoratchi-agent"
	systemUser     = "nazoratchi"
	dockerProxyCtr = "nazoratchi-docker-proxy"
)

// exitError — maxsus chiqish kodi (xabar allaqachon chop etilgan bo'lsa Msg bo'sh).
type exitError struct {
	Code int
	Msg  string
}

func (e *exitError) Error() string { return e.Msg }

// Runner — tashqi buyruqlarni ishga tushirish (testda soxta bilan almashtiriladi).
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

type execRunner struct{}

func (execRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	return exec.CommandContext(ctx, name, args...).CombinedOutput()
}

// uninstaller — barcha bog'liqliklar kiritiladi, shunda test haqiqiy tizimga tegmaydi.
type uninstaller struct {
	Root     string // fayl yo'llari ildizi ("" yoki "/" — haqiqiy tizim); testda tmp
	Run      Runner
	Out      io.Writer
	Geteuid  func() int
	Exe      string // joriy binar yo'li (mantiqiy)
	Version  string
	Goodbye  func(ctx context.Context, coreURL, caFile, token, version string) error
	Purge    bool
	ConfPath string
}

// resolve mantiqiy yo'lni ildiz ostidagi haqiqiy yo'lga aylantiradi; ildizdan chiqib ketsa xato.
func (u *uninstaller) resolve(logical string) (string, error) {
	clean := filepath.Clean(logical)
	if u.Root == "" || u.Root == "/" {
		return clean, nil
	}
	full := filepath.Join(u.Root, clean)
	rel, err := filepath.Rel(u.Root, full)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("yo'l ildizdan tashqarida: %s", logical)
	}
	return full, nil
}

func (u *uninstaller) warnf(format string, a ...any) {
	fmt.Fprintf(u.Out, "ogohlantirish: "+format+"\n", a...)
}

func (u *uninstaller) say(format string, a ...any) { fmt.Fprintf(u.Out, format+"\n", a...) }

// binaryRemovable binar faqat /usr/local/bin/ ichida bo'lsagina o'chiriladi.
func binaryRemovable(exe string) bool {
	clean := filepath.ToSlash(filepath.Clean(exe))
	return strings.HasPrefix(clean, binDir) && clean != strings.TrimSuffix(binDir, "/")
}

func (u *uninstaller) plan() []string {
	p := []string{
		"core'ga xayrlashuv xabari yuboriladi (host arxivlanadi)",
		"systemd servisi to'xtatiladi va o'chiriladi: " + serviceName,
		"unit fayli o'chiriladi: " + unitPath,
		"sozlama va token o'chiriladi: " + configDir,
		"holat papkasi o'chiriladi: " + stateDir,
		"yangilanish holati va o'rov skripti o'chiriladi: " + updateStateDir + ", " + prestartDir,
		"tizim foydalanuvchisi o'chiriladi: " + systemUser,
	}
	if u.Purge {
		p = append(p, "docker konteyneri o'chiriladi: "+dockerProxyCtr)
	}
	if binaryRemovable(u.Exe) {
		p = append(p, "binar o'chiriladi: "+u.Exe)
	}
	return p
}

// Do o'chirish qadamlarini bajaradi. Xatolar (goodbye, systemctl, userdel...) ogohlantirish bo'ladi va
// jarayon davom etadi; faqat root emasligi yoki tasdiqsizlik to'xtatadi.
func (u *uninstaller) Do(ctx context.Context, yes bool) error {
	if u.Geteuid() != 0 {
		return errors.New("o'chirish uchun root huquqi kerak (sudo bilan ishga tushiring)")
	}
	if !yes {
		u.say("Quyidagilar o'chiriladi:")
		for _, s := range u.plan() {
			u.say("  - %s", s)
		}
		u.say("Davom etish uchun --yes bering.")
		return &exitError{Code: 2}
	}

	u.sayGoodbye(ctx)

	if out, err := u.Run.Run(ctx, "systemctl", "disable", "--now", serviceName); err != nil {
		u.warnf("servisni to'xtatib bo'lmadi: %v %s", err, strings.TrimSpace(string(out)))
	} else {
		u.say("servis to'xtatildi va o'chirildi")
	}
	u.removePath(unitPath, false)
	if out, err := u.Run.Run(ctx, "systemctl", "daemon-reload"); err != nil {
		u.warnf("daemon-reload bajarilmadi: %v %s", err, strings.TrimSpace(string(out)))
	}
	u.removePath(configDir, true)
	u.removePath(stateDir, true)
	u.removePath(updateStateDir, true)
	u.removePath(prestartDir, true)

	if out, err := u.Run.Run(ctx, "userdel", systemUser); err != nil {
		u.warnf("%s foydalanuvchisini o'chirib bo'lmadi: %v %s", systemUser, err, strings.TrimSpace(string(out)))
	} else {
		u.say("foydalanuvchi o'chirildi: %s", systemUser)
	}
	if u.Purge {
		if out, err := u.Run.Run(ctx, "docker", "rm", "-f", dockerProxyCtr); err != nil {
			u.warnf("docker konteynerini o'chirib bo'lmadi: %v %s", err, strings.TrimSpace(string(out)))
		} else {
			u.say("docker konteyneri o'chirildi: %s", dockerProxyCtr)
		}
	}
	// Binar OXIRIDA: undan keyin hech narsa qolmaydi.
	if binaryRemovable(u.Exe) {
		u.removePath(u.Exe+".old", false) // o'z-o'zini yangilashdan qolgan zaxira nusxa
		u.removePath(u.Exe, false)
	} else {
		u.warnf("binar %s ichida emas, qo'lda o'chiring: %s", binDir, u.Exe)
	}
	u.say("Nazoratchi agenti o'chirildi.")
	return nil
}

func (u *uninstaller) sayGoodbye(ctx context.Context) {
	confReal, err := u.resolve(u.ConfPath)
	if err != nil {
		u.warnf("goodbye o'tkazib yuborildi: %v", err)
		return
	}
	cfg, err := config.Load(confReal)
	if err != nil {
		u.warnf("goodbye o'tkazib yuborildi, sozlama o'qilmadi: %v", err)
		return
	}
	tokReal, err := u.resolve(cfg.Core.TokenFile)
	if err != nil {
		u.warnf("goodbye o'tkazib yuborildi: %v", err)
		return
	}
	raw, err := os.ReadFile(tokReal)
	token := strings.TrimSpace(string(raw))
	if err != nil || token == "" {
		u.warnf("goodbye o'tkazib yuborildi: token o'qilmadi")
		return
	}
	gctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := u.Goodbye(gctx, cfg.Core.URL, cfg.Core.CAFile, token, u.Version); err != nil {
		u.warnf("core'ga xabar berib bo'lmadi (hostni panelda qo'lda arxivlang): %v", err)
		return
	}
	u.say("core'ga xabar berildi (host arxivlandi)")
}

func (u *uninstaller) removePath(logical string, all bool) {
	real, err := u.resolve(logical)
	if err != nil {
		u.warnf("%v", err)
		return
	}
	if real == "/" || real == "" || real == filepath.Clean(u.Root) {
		u.warnf("xavfli yo'l o'chirilmadi: %s", logical)
		return
	}
	if _, err := os.Lstat(real); errors.Is(err, os.ErrNotExist) {
		return
	}
	var rmErr error
	if all {
		rmErr = os.RemoveAll(real)
	} else {
		rmErr = os.Remove(real)
	}
	if rmErr != nil {
		u.warnf("o'chirib bo'lmadi %s: %v", logical, rmErr)
		return
	}
	u.say("o'chirildi: %s", logical)
}

func cmdUninstall(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("uninstall", flag.ContinueOnError)
	path := configFlag(fs)
	purge := fs.Bool("purge", false, "docker-socket-proxy konteynerini ham o'chirish")
	yes := fs.Bool("yes", false, "tasdiqlash (usiz faqat ro'yxat ko'rsatiladi)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	exe, _ := os.Executable()
	if resolved, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolved
	}
	u := &uninstaller{
		Run: execRunner{}, Out: out, Geteuid: os.Geteuid, Exe: exe, Version: version,
		Goodbye: sender.Goodbye, Purge: *purge, ConfPath: *path,
	}
	return u.Do(context.Background(), *yes)
}
