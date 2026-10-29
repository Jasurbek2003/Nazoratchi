package collector

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// F2 qismi (TZ 7.4.1): jarayonlar, fayl deskriptorlari, swap faolligi va yadro OOM hisoblagichi.
// Bu fayllar eski yadro yoki soddalashtirilgan muhitda bo'lmasligi mumkin: yo'qligi xato emas.

func (s *System) f2(o *out, now time.Time) error {
	var errs []error
	if err := s.procs(o); err != nil {
		errs = append(errs, fmt.Errorf("procs: %w", err))
	}
	if err := s.fds(o); err != nil {
		errs = append(errs, fmt.Errorf("fd: %w", err))
	}
	if err := s.vmstat(o, now); err != nil {
		errs = append(errs, fmt.Errorf("vmstat: %w", err))
	}
	return errors.Join(errs...)
}

// procs: `/proc/stat` dan ishlayotgan/bloklangan, `/proc/loadavg` dan threadlar jami, `/proc/[pid]/stat`
// dan jarayonlar va zombilar soni. Bitta jarayon yo'qolib qolishi (o'qish paytida tugagan) normal holat.
func (s *System) procs(o *out) error {
	if data, err := os.ReadFile(filepath.Join(s.proc, "stat")); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			f := strings.Fields(line)
			if len(f) != 2 {
				continue
			}
			if f[0] == "procs_running" || f[0] == "procs_blocked" {
				if v, err := strconv.ParseFloat(f[1], 64); err == nil {
					o.add(f[0], v)
				}
			}
		}
	}
	if data, err := os.ReadFile(filepath.Join(s.proc, "loadavg")); err == nil {
		if f := strings.Fields(string(data)); len(f) >= 4 {
			if _, total, ok := strings.Cut(f[3], "/"); ok {
				if v, err := strconv.ParseFloat(total, 64); err == nil {
					o.add("threads_total", v)
				}
			}
		}
	}
	entries, err := os.ReadDir(s.proc)
	if err != nil {
		return err
	}
	total, zombies := 0, 0
	for _, e := range entries {
		if !e.IsDir() || !isPID(e.Name()) {
			continue
		}
		b, err := os.ReadFile(filepath.Join(s.proc, e.Name(), "stat"))
		if err != nil {
			continue
		}
		total++
		if procState(b) == 'Z' {
			zombies++
		}
	}
	if total == 0 {
		return nil // `/proc/[pid]` yo'q (soddalashtirilgan muhit)
	}
	o.add("procs_total", float64(total))
	o.add("procs_zombie", float64(zombies))
	return nil
}

func isPID(name string) bool {
	if name == "" {
		return false
	}
	for _, r := range name {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

// procState `pid (comm) S ...` qatoridan holat harfini oladi. `comm` ichida qavs va bo'shliq bo'lishi
// mumkin, shuning uchun oxirgi `)` dan keyin qaraladi.
func procState(stat []byte) byte {
	i := strings.LastIndexByte(string(stat), ')')
	if i < 0 || i+2 >= len(stat) {
		return 0
	}
	return stat[i+2]
}

func (s *System) fds(o *out) error {
	data, err := os.ReadFile(filepath.Join(s.proc, "sys/fs/file-nr"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	f := strings.Fields(string(data))
	if len(f) < 3 {
		return errors.New("file-nr formati noto'g'ri")
	}
	alloc, err1 := strconv.ParseFloat(f[0], 64)
	max, err2 := strconv.ParseFloat(f[2], 64)
	if err1 != nil || err2 != nil {
		return errors.New("file-nr qiymati son emas")
	}
	o.add("fd_allocated", alloc)
	o.add("fd_max", max)
	return nil
}

// vmstat: `oom_kill` to'g'ridan-to'g'ri (hisoblagich), `pswpin/pswpout` esa soniyadagi tezlikka aylantiriladi.
func (s *System) vmstat(o *out, now time.Time) error {
	data, err := os.ReadFile(filepath.Join(s.proc, "vmstat"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	var swapIn, swapOut float64
	var haveSwap bool
	for _, line := range strings.Split(string(data), "\n") {
		k, v, ok := strings.Cut(line, " ")
		if !ok {
			continue
		}
		val, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
		if err != nil {
			continue
		}
		switch k {
		case "oom_kill":
			o.add("oom_kill_total", val)
		case "pswpin":
			swapIn, haveSwap = val, true
		case "pswpout":
			swapOut = val
		}
	}
	if !haveSwap {
		return nil
	}
	dt := now.Sub(s.vmAt).Seconds()
	if s.haveVm && dt > 0 && swapIn >= s.prevSwapIn && swapOut >= s.prevSwapOut { // kamaysa: reboot, o'lchov tashlanadi
		o.add("swap_in_pages_per_sec", (swapIn-s.prevSwapIn)/dt)
		o.add("swap_out_pages_per_sec", (swapOut-s.prevSwapOut)/dt)
	}
	s.prevSwapIn, s.prevSwapOut, s.vmAt, s.haveVm = swapIn, swapOut, now, true
	return nil
}
