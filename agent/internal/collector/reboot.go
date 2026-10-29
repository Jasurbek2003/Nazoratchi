package collector

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"time"

	"nazoratchi/agent/internal/facts"
	"nazoratchi/agent/internal/metric"
)

// Reboot — kutilayotgan reboot va kernel farqi (TZ 7.4.8, FR-HST-009).
// `reboot_required`: /var/run/reboot-required bor-yo'qligi; `kernel_reboot_pending`: o'rnatilgan eng
// yangi kernel ishlayotganidan yuqori (yangilash o'rnatilgan, lekin hali yuklanmagan).
type Reboot struct {
	proc, flagFile, bootDir string
}

func NewReboot(proc, flagFile, bootDir string) *Reboot {
	return &Reboot{proc: proc, flagFile: flagFile, bootDir: bootDir}
}

func (r *Reboot) Name() string { return "reboot" }

func (r *Reboot) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	o := newOut(now)
	required, age := 0.0, 0.0
	if st, err := os.Stat(r.flagFile); err == nil {
		required = 1
		age = max(0, now.Sub(st.ModTime()).Seconds())
	}
	o.add("reboot_required", required)
	o.add("reboot_required_age_seconds", age)

	pending := 0.0
	if b, err := os.ReadFile(filepath.Join(r.proc, "sys/kernel/osrelease")); err == nil {
		if facts.KernelBehind(strings.TrimSpace(string(b)), facts.LatestKernel(r.bootDir)) {
			pending = 1
		}
	}
	o.add("kernel_reboot_pending", pending)
	return o.s, nil
}
