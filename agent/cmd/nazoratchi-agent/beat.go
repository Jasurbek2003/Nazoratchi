package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"nazoratchi/agent/internal/collector"
)

// cmdBeat: `nazoratchi-agent beat <job> [--dir ...]` — cron skript oxirida chaqiradi (FR-SVC-004).
func cmdBeat(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("beat", flag.ContinueOnError)
	dir := fs.String("dir", collector.DefaultHeartbeatsDir, "heartbeat papkasi")
	// Job nomi opsiyadan oldin ham, keyin ham kelishi mumkin: `beat backup --dir X` va `beat --dir X backup`.
	var job string
	rest := args
	for len(rest) > 0 {
		if err := fs.Parse(rest); err != nil {
			return err
		}
		rest = fs.Args()
		if len(rest) == 0 {
			break
		}
		if job != "" {
			return fmt.Errorf("ortiqcha argument: %q", rest[0])
		}
		job, rest = rest[0], rest[1:]
	}
	if job == "" {
		return fmt.Errorf("foydalanish: nazoratchi-agent beat <job> [--dir %s]", collector.DefaultHeartbeatsDir)
	}
	if err := writeBeat(*dir, job, time.Now()); err != nil {
		return err
	}
	fmt.Fprintf(out, "heartbeat yozildi: %s\n", filepath.Join(*dir, job))
	return nil
}

// writeBeat `<dir>/<job>` ni atomik yozadi (tmp + rename), rejim 0644; papka yo'q bo'lsa 0755 bilan yaratadi.
// Vaqtinchalik fayl nuqta bilan boshlanadi, shuning uchun kollektor uni hech qachon ko'rmaydi.
func writeBeat(dir, job string, now time.Time) error {
	if !collector.ValidJobName(job) {
		return fmt.Errorf("job nomi yaroqsiz: %q (harf, raqam, _ . @ -; 1..80 belgi, nuqta bilan boshlanmaydi, .tmp bilan tugamaydi)", job)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil { //nolint:gosec // heartbeat'larni agent (boshqa foydalanuvchi) o'qishi kerak
		return err
	}
	f, err := os.CreateTemp(dir, ".beat-*.tmp")
	if err != nil {
		return err
	}
	tmp := f.Name()
	fail := func(err error) error {
		f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if _, err := f.WriteString(now.UTC().Format(time.RFC3339) + "\n"); err != nil {
		return fail(err)
	}
	if err := f.Chmod(0o644); err != nil {
		return fail(err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, filepath.Join(dir, job)); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}
