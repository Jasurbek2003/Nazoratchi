package collector

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

const (
	// DefaultHeartbeatsDir — cron skriptlar `nazoratchi-agent beat <job>` bilan yozadigan papka (FR-SVC-004).
	DefaultHeartbeatsDir = "/var/lib/nazoratchi/heartbeats"
	maxHeartbeats        = 200
	maxSystemctlOutput   = 16 << 10
)

var (
	unitNameRe = regexp.MustCompile(`^[A-Za-z0-9:_.@\-]{1,100}$`)
	jobNameRe  = regexp.MustCompile(`^[A-Za-z0-9_.@\-]{1,80}$`)
)

// ValidUnitName systemd unit nomini tekshiradi. `-` bilan boshlanmaydi: nom `systemctl` ga argument
// sifatida beriladi va opsiya deb o'qilmasligi kerak.
func ValidUnitName(s string) bool { return unitNameRe.MatchString(s) && s[0] != '-' }

// ValidJobName cron heartbeat nomini tekshiradi: fayl nomi bo'ladi, shuning uchun nuqta bilan boshlanmaydi
// (yashirin fayl, `..`) va `.tmp` bilan tugamaydi.
func ValidJobName(s string) bool {
	return jobNameRe.MatchString(s) && s[0] != '.' && !strings.HasSuffix(s, ".tmp")
}

// Runner tashqi buyruqni shellsiz ishga tushiradi va stdout ni qaytaradi (testlarda soxtalashtiriladi).
type Runner func(ctx context.Context, name string, args ...string) ([]byte, error)

func execRunner(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	var stdout bytes.Buffer
	cmd.Stdout = &limitedWriter{w: &stdout, left: maxSystemctlOutput}
	if err := cmd.Run(); err != nil {
		return nil, err
	}
	return stdout.Bytes(), nil
}

type limitedWriter struct {
	w    *bytes.Buffer
	left int
}

func (l *limitedWriter) Write(p []byte) (int, error) {
	n := len(p)
	if len(p) > l.left {
		p = p[:l.left]
	}
	l.left -= len(p)
	l.w.Write(p)
	return n, nil // ortiqchasi tashlanadi, jarayon bloklanmaydi
}

// Systemd — sozlamadagi unit lar holati va cron heartbeat'lar (TZ 7.4.5, F1).
type Systemd struct {
	units         []string
	heartbeatsDir string
	run           Runner
}

// NewSystemd: run == nil bo'lsa haqiqiy `systemctl` ishlatiladi. Yaroqsiz unit nomi xato.
func NewSystemd(units []string, heartbeatsDir string, run Runner) (*Systemd, error) {
	for _, u := range units {
		if !ValidUnitName(u) {
			return nil, fmt.Errorf("systemd unit nomi yaroqsiz: %q", u)
		}
	}
	if run == nil {
		run = execRunner
	}
	return &Systemd{units: units, heartbeatsDir: heartbeatsDir, run: run}, nil
}

func (s *Systemd) Name() string { return "systemd" }

func (s *Systemd) Collect(ctx context.Context, now time.Time) ([]metric.Sample, error) {
	o := newOut(now)
	var errs []error
	for _, u := range s.units {
		if !ValidUnitName(u) { // chuqur himoya: konstruktorsiz yaratilgan bo'lsa ham
			errs = append(errs, fmt.Errorf("systemd unit nomi yaroqsiz: %q", u))
			continue
		}
		data, err := s.run(ctx, "systemctl", "show", u, "--property=ActiveState,LoadState,SubState")
		if err != nil {
			errs = append(errs, fmt.Errorf("systemctl show %s: %w", u, err))
			continue
		}
		props := parseProps(data)
		active, failed := 0.0, 0.0
		if props["LoadState"] != "not-found" {
			switch props["ActiveState"] {
			case "active":
				active = 1
			case "failed":
				failed = 1
			}
		}
		o.add("systemd_unit_active", active, "unit", u)
		o.add("systemd_unit_failed", failed, "unit", u)
	}
	if err := s.heartbeats(o); err != nil {
		errs = append(errs, err)
	}
	return o.s, errors.Join(errs...)
}

func parseProps(data []byte) map[string]string {
	m := map[string]string{}
	for _, line := range strings.Split(string(data), "\n") {
		if k, v, ok := strings.Cut(strings.TrimSpace(line), "="); ok {
			m[k] = v
		}
	}
	return m
}

// heartbeats: faqat oddiy fayllar (simvolik havolalar kuzatilmaydi); papka yo'q bo'lsa xato emas.
func (s *Systemd) heartbeats(o *out) error {
	if s.heartbeatsDir == "" {
		return nil
	}
	entries, err := os.ReadDir(s.heartbeatsDir)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("heartbeat papkasi o'qilmadi: %w", err)
	}
	var errs []error
	n := 0
	for _, e := range entries {
		if !e.Type().IsRegular() || !ValidJobName(e.Name()) {
			continue
		}
		if n++; n > maxHeartbeats {
			errs = append(errs, fmt.Errorf("heartbeat fayllari %d dan ko'p, ortiqchasi o'tkazib yuborildi", maxHeartbeats))
			break
		}
		info, err := e.Info()
		if err != nil {
			errs = append(errs, fmt.Errorf("heartbeat %s: %w", e.Name(), err))
			continue
		}
		o.add("cron_job_last_success_timestamp", float64(info.ModTime().UnixNano())/1e9, "job", e.Name())
	}
	return errors.Join(errs...)
}
