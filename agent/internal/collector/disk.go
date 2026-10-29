package collector

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

// FsStat — `statfs` natijasi (bloklar soni va hajmi).
type FsStat struct {
	BlockSize uint64
	Blocks    uint64
	Bfree     uint64
	Bavail    uint64
	Files     uint64 // inode lar jami (0 — fayl tizimi inode hisoblamaydi, masalan btrfs)
	Ffree     uint64
}

// StatFunc testlarda almashtiriladi; ishlab chiqarishda `statfs(2)`.
type StatFunc func(mountpoint string) (FsStat, error)

// Haqiqiy diskni ko'rsatmaydigan fayl tizimlari (TZ 7.4.2). Sozlamadagi ro'yxat shunga qo'shiladi.
var pseudoFS = []string{
	"proc", "sysfs", "cgroup", "cgroup2", "devpts", "devtmpfs", "tmpfs", "overlay", "squashfs",
	"mqueue", "debugfs", "tracefs", "securityfs", "pstore", "bpf", "autofs", "fusectl",
	"configfs", "hugetlbfs", "binfmt_misc", "nsfs", "ramfs", "efivarfs",
}

// Disk — fayl tizimlari hajmi va faqat-o'qish holati (TZ 7.4.2, F1 qismi).
type Disk struct {
	proc   string
	ignore map[string]bool
	stat   StatFunc
}

func NewDisk(proc string, ignoreFS []string, stat StatFunc) *Disk {
	ig := make(map[string]bool, len(pseudoFS)+len(ignoreFS))
	for _, k := range pseudoFS {
		ig[k] = true
	}
	for _, k := range ignoreFS {
		ig[k] = true
	}
	if stat == nil {
		stat = statfs
	}
	return &Disk{proc: proc, ignore: ig, stat: stat}
}

func (d *Disk) Name() string { return "disk" }

type mount struct {
	device, point, fstype string
	readonly              bool
}

func (d *Disk) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	mounts, err := d.mounts()
	if err != nil {
		return nil, err
	}
	o := newOut(now)
	var errs []error
	for _, m := range mounts {
		st, err := d.stat(m.point)
		if err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", m.point, err))
			continue
		}
		bs := float64(st.BlockSize)
		total := float64(st.Blocks) * bs
		used := float64(st.Blocks-min(st.Blocks, st.Bfree)) * bs
		avail := float64(st.Bavail) * bs
		l := []string{"mount", m.point, "device", m.device, "fstype", m.fstype}
		o.add("fs_total_bytes", total, l...)
		o.add("fs_used_bytes", used, l...)
		o.add("fs_avail_bytes", avail, l...)
		if used+avail > 0 { // `df` ga mos: used / (used + avail)
			o.add("fs_used_percent", percent(100*used/(used+avail)), l...)
		}
		if st.Files > 0 { // FR-HST-008
			inUsed := float64(st.Files - min(st.Files, st.Ffree))
			o.add("fs_inodes_total", float64(st.Files), l...)
			o.add("fs_inodes_used", inUsed, l...)
			o.add("fs_inodes_used_percent", percent(100*inUsed/float64(st.Files)), l...)
		}
		ro := 0.0
		if m.readonly {
			ro = 1
		}
		o.add("fs_readonly", ro, "mount", m.point, "device", m.device)
	}
	return o.s, errors.Join(errs...)
}

// mounts `/proc/mounts` dan haqiqiy fayl tizimlarini oladi. Bir qurilma bir necha joyga ulangan
// bo'lsa (bind mount, Docker), birinchisi qoladi.
func (d *Disk) mounts() ([]mount, error) {
	data, err := os.ReadFile(filepath.Join(d.proc, "mounts"))
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	var out []mount
	for _, line := range strings.Split(string(data), "\n") {
		f := strings.Fields(line)
		if len(f) < 4 {
			continue
		}
		m := mount{device: unescapeMount(f[0]), point: unescapeMount(f[1]), fstype: f[2]}
		if d.ignore[m.fstype] || seen[m.device] {
			continue
		}
		for _, opt := range strings.Split(f[3], ",") {
			if opt == "ro" {
				m.readonly = true
			}
		}
		seen[m.device] = true
		out = append(out, m)
	}
	return out, nil
}

// unescapeMount `/proc/mounts` dagi sakkizlik ketma-ketliklarni (`\040` = bo'shliq) ochadi.
func unescapeMount(s string) string {
	if !strings.Contains(s, `\`) {
		return s
	}
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] == '\\' && i+3 < len(s) {
			if v, err := strconv.ParseUint(s[i+1:i+4], 8, 8); err == nil {
				b.WriteByte(byte(v))
				i += 3
				continue
			}
		}
		b.WriteByte(s[i])
	}
	return b.String()
}

// matchAny `ignore_ifaces` kabi glob ro'yxatlar uchun.
func matchAny(patterns []string, name string) bool {
	for _, p := range patterns {
		if ok, _ := path.Match(p, name); ok {
			return true
		}
	}
	return false
}
