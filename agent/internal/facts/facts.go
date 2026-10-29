// Package facts — kam o'zgaradigan host ma'lumotlari (TZ 7.4.10). Metrika emas: JSON obyekt sifatida
// birinchi paketda va keyin o'zgarganda (yoki 10 daqiqada bir) yuboriladi.
package facts

import (
	"bufio"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

// Source fayl yo'llari; testlarda almashtiriladi.
type Source struct {
	Proc       string // /proc
	OSRelease  string // /etc/os-release
	BootDir    string // /boot
	HostName   func() (string, error)
	NameConfig string // sozlamadagi host.name (bo'sh bo'lsa hostname)
}

func Default(nameOverride string) Source {
	return Source{Proc: "/proc", OSRelease: "/etc/os-release", BootDir: "/boot", HostName: os.Hostname, NameConfig: nameOverride}
}

// Collect topilgan faktlarni qaytaradi; o'qib bo'lmaganlari tushirib qoldiriladi.
func (s Source) Collect() map[string]any {
	f := map[string]any{"arch": runtime.GOARCH}
	if s.NameConfig != "" {
		f["hostname"] = s.NameConfig
	} else if h, err := s.HostName(); err == nil && h != "" {
		f["hostname"] = h
	}
	if v := osPrettyName(s.OSRelease); v != "" {
		f["os"] = v
	}
	if v := readTrim(filepath.Join(s.Proc, "sys/kernel/osrelease")); v != "" {
		f["kernel_running"] = v
	}
	if v := LatestKernel(s.BootDir); v != "" {
		f["kernel_latest_installed"] = v
	}
	if v := readTrim(filepath.Join(s.Proc, "sys/kernel/random/boot_id")); v != "" {
		f["boot_id"] = v
	}
	model, count := cpuInfo(filepath.Join(s.Proc, "cpuinfo"))
	if model != "" {
		f["cpu_model"] = model
	}
	if count > 0 {
		f["cpu_count"] = count
	}
	if v := memTotal(filepath.Join(s.Proc, "meminfo")); v > 0 {
		f["mem_total_bytes"] = v
	}
	return f
}

func readTrim(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

func osPrettyName(path string) string {
	file, err := os.Open(path)
	if err != nil {
		return ""
	}
	defer file.Close()
	sc := bufio.NewScanner(file)
	for sc.Scan() {
		if v, ok := strings.CutPrefix(sc.Text(), "PRETTY_NAME="); ok {
			return strings.Trim(v, `"'`)
		}
	}
	return ""
}

func cpuInfo(path string) (model string, count int) {
	file, err := os.Open(path)
	if err != nil {
		return "", 0
	}
	defer file.Close()
	sc := bufio.NewScanner(file)
	for sc.Scan() {
		key, val, ok := strings.Cut(sc.Text(), ":")
		if !ok {
			continue
		}
		switch strings.TrimSpace(key) {
		case "processor":
			count++
		case "model name":
			if model == "" {
				model = strings.TrimSpace(val)
			}
		}
	}
	return model, count
}

func memTotal(path string) int64 {
	file, err := os.Open(path)
	if err != nil {
		return 0
	}
	defer file.Close()
	sc := bufio.NewScanner(file)
	for sc.Scan() {
		if rest, ok := strings.CutPrefix(sc.Text(), "MemTotal:"); ok {
			fields := strings.Fields(rest)
			if len(fields) > 0 {
				if kb, err := strconv.ParseInt(fields[0], 10, 64); err == nil {
					return kb * 1024
				}
			}
		}
	}
	return 0
}

var digits = regexp.MustCompile(`\d+`)

// LatestKernel `/boot/vmlinuz-*` ichidan eng yuqori versiyani qaytaradi (FR-HST-009: reboot kutilmoqda).
func LatestKernel(bootDir string) string {
	matches, _ := filepath.Glob(filepath.Join(bootDir, "vmlinuz-*"))
	var versions []string
	for _, m := range matches {
		versions = append(versions, strings.TrimPrefix(filepath.Base(m), "vmlinuz-"))
	}
	if len(versions) == 0 {
		return ""
	}
	sort.Slice(versions, func(i, j int) bool { return versionLess(versions[i], versions[j]) })
	return versions[len(versions)-1]
}

// KernelBehind ishlayotgan kernel o'rnatilgan eng yangisidan eski bo'lsa true (reboot kutilmoqda).
// Ikkalasidan biri noma'lum bo'lsa false: noto'g'ri signal berishdan ko'ra jim turgan yaxshi.
func KernelBehind(running, latest string) bool {
	return running != "" && latest != "" && running != latest && versionLess(running, latest)
}

// versionLess raqamli qismlarni son sifatida solishtiradi (`6.8.0-9` < `6.8.0-147`).
func versionLess(a, b string) bool {
	pa, pb := digits.FindAllString(a, -1), digits.FindAllString(b, -1)
	for i := 0; i < len(pa) && i < len(pb); i++ {
		x, _ := strconv.Atoi(pa[i])
		y, _ := strconv.Atoi(pb[i])
		if x != y {
			return x < y
		}
	}
	if len(pa) != len(pb) {
		return len(pa) < len(pb)
	}
	return a < b
}
