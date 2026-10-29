package collector

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

type cpuTimes [8]uint64

var cpuModes = [8]string{"user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"}

// System — CPU, yuklama, xotira, swap, uptime (TZ 7.4.1, F1 qismi).
type System struct {
	proc     string
	prev     cpuTimes
	havePrev bool

	prevSwapIn, prevSwapOut float64 // /proc/vmstat: oldingi o'lchov (tezlik uchun)
	vmAt                    time.Time
	haveVm                  bool
}

func NewSystem(proc string) *System { return &System{proc: proc} }

func (s *System) Name() string { return "system" }

func (s *System) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	o := newOut(now)
	var errs []error
	cores, err := s.cpu(o)
	if err != nil {
		errs = append(errs, fmt.Errorf("cpu: %w", err))
	}
	if cores == 0 {
		cores = runtime.NumCPU()
	}
	if err := s.load(o, cores); err != nil {
		errs = append(errs, fmt.Errorf("load: %w", err))
	}
	if err := s.mem(o); err != nil {
		errs = append(errs, fmt.Errorf("mem: %w", err))
	}
	if err := s.uptime(o); err != nil {
		errs = append(errs, fmt.Errorf("uptime: %w", err))
	}
	if err := s.f2(o, now); err != nil {
		errs = append(errs, err)
	}
	return o.s, errors.Join(errs...)
}

// cpu `/proc/stat` ning ikki o'lchovi farqidan foizlarni hisoblaydi. Birinchi chaqiruv faqat
// boshlang'ich qiymatni eslab qoladi. Hisoblagich qayta boshlansa (reboot) o'lchov tashlanadi.
func (s *System) cpu(o *out) (int, error) {
	data, err := os.ReadFile(filepath.Join(s.proc, "stat"))
	if err != nil {
		return 0, err
	}
	var cur cpuTimes
	found, cores := false, 0
	for _, line := range strings.Split(string(data), "\n") {
		f := strings.Fields(line)
		if len(f) < 2 {
			continue
		}
		switch {
		case f[0] == "cpu":
			if len(f) < 9 {
				return 0, errors.New("cpu qatori qisqa")
			}
			for i := range cur {
				v, err := strconv.ParseUint(f[i+1], 10, 64)
				if err != nil {
					return 0, err
				}
				cur[i] = v
			}
			found = true
		case strings.HasPrefix(f[0], "cpu") && f[0][3] >= '0' && f[0][3] <= '9':
			cores++
		case f[0] == "btime":
			if v, err := strconv.ParseFloat(f[1], 64); err == nil {
				o.add("boot_time_seconds", v)
			}
		}
	}
	if !found {
		return cores, errors.New("cpu qatori topilmadi")
	}
	if s.havePrev {
		var d cpuTimes
		var total uint64
		reset := false
		for i := range cur {
			if cur[i] < s.prev[i] {
				reset = true
				break
			}
			d[i] = cur[i] - s.prev[i]
			total += d[i]
		}
		if !reset && total > 0 {
			for i, mode := range cpuModes {
				o.add("cpu_usage_percent", percent(100*float64(d[i])/float64(total)), "mode", mode)
			}
			idle := d[3] + d[4] // idle + iowait
			o.add("cpu_busy_percent", percent(100-100*float64(idle)/float64(total)))
		}
	}
	s.prev, s.havePrev = cur, true
	return cores, nil
}

func (s *System) load(o *out, cores int) error {
	data, err := os.ReadFile(filepath.Join(s.proc, "loadavg"))
	if err != nil {
		return err
	}
	f := strings.Fields(string(data))
	if len(f) < 3 {
		return errors.New("loadavg formati noto'g'ri")
	}
	var v [3]float64
	for i := range v {
		if v[i], err = strconv.ParseFloat(f[i], 64); err != nil {
			return err
		}
	}
	o.add("load1", v[0])
	o.add("load5", v[1])
	o.add("load15", v[2])
	o.add("load_per_core_1m", v[0]/float64(cores))
	return nil
}

func (s *System) mem(o *out) error {
	data, err := os.ReadFile(filepath.Join(s.proc, "meminfo"))
	if err != nil {
		return err
	}
	m := map[string]float64{}
	for _, line := range strings.Split(string(data), "\n") {
		key, rest, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		f := strings.Fields(rest)
		if len(f) == 0 {
			continue
		}
		v, err := strconv.ParseFloat(f[0], 64)
		if err != nil {
			continue
		}
		if len(f) > 1 && f[1] == "kB" {
			v *= 1024
		}
		m[key] = v
	}
	total, okT := m["MemTotal"]
	avail, okA := m["MemAvailable"]
	if !okT || !okA || total <= 0 {
		return errors.New("MemTotal/MemAvailable topilmadi")
	}
	used := total - avail
	o.add("mem_total_bytes", total)
	o.add("mem_available_bytes", avail)
	o.add("mem_used_bytes", used)
	o.add("mem_used_percent", percent(100*used/total))
	if free, ok := m["MemFree"]; ok {
		o.add("mem_free_bytes", free)
	}
	if swapTotal, ok := m["SwapTotal"]; ok {
		swapUsed := swapTotal - m["SwapFree"]
		o.add("swap_total_bytes", swapTotal)
		o.add("swap_used_bytes", swapUsed)
		pct := 0.0
		if swapTotal > 0 {
			pct = percent(100 * swapUsed / swapTotal)
		}
		o.add("swap_used_percent", pct)
	}
	return nil
}

func (s *System) uptime(o *out) error {
	data, err := os.ReadFile(filepath.Join(s.proc, "uptime"))
	if err != nil {
		return err
	}
	f := strings.Fields(string(data))
	if len(f) < 1 {
		return errors.New("uptime formati noto'g'ri")
	}
	v, err := strconv.ParseFloat(f[0], 64)
	if err != nil {
		return err
	}
	o.add("uptime_seconds", v)
	return nil
}
