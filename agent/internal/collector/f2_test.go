package collector

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"nazoratchi/agent/internal/metric"
)

func TestSystemProcsFDAndOOM(t *testing.T) {
	root := writeProc(t, map[string]string{
		"stat":           statA + "procs_running 3\nprocs_blocked 1\n",
		"loadavg":        "0 0 0 3/412 99\n",
		"meminfo":        meminfo,
		"uptime":         "1 1",
		"1/stat":         "1 (systemd) S 0 1 1 0 -1\n",
		"2/stat":         "2 (my (weird) name) Z 1 2 2 0 -1\n", // qavsli nom + zombi
		"3/stat":         "3 (kworker/0:1) I 2 0 0 0 -1\n",
		"sys/fs/file-nr": "1824\t0\t9223372036854775807\n",
		"vmstat":         "pswpin 100\npswpout 200\noom_kill 4\n",
		"4/notpid":       "x",
	})
	if err := os.MkdirAll(filepath.Join(root, "self"), 0o750); err != nil {
		t.Fatal(err)
	}
	got, err := NewSystem(root).Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	for name, want := range map[string]float64{
		"procs_total": 3, "procs_zombie": 1, "procs_running": 3, "procs_blocked": 1,
		"threads_total": 412, "fd_allocated": 1824, "oom_kill_total": 4,
	} {
		if v, ok := m[name]; !ok || !approx(v.V, want) {
			t.Errorf("%s = %+v, kutilgan %v", name, v, want)
		}
	}
	if _, ok := m["swap_in_pages_per_sec"]; ok {
		t.Error("birinchi o'lchovda swap tezligi bo'lmasligi kerak")
	}
}

func TestSystemSwapRatesAndReset(t *testing.T) {
	base := map[string]string{"stat": statA, "loadavg": "0 0 0 1/1 1", "meminfo": meminfo, "uptime": "1 1"}
	write := func(root, vm string) {
		if err := os.WriteFile(filepath.Join(root, "vmstat"), []byte(vm), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	root := writeProc(t, base)
	write(root, "pswpin 100\npswpout 200\n")
	s := NewSystem(root)
	t0 := time.Unix(1_000_000, 0)
	_, _ = s.Collect(context.Background(), t0)

	write(root, "pswpin 400\npswpout 260\n")
	got, _ := s.Collect(context.Background(), t0.Add(10*time.Second))
	m := byName(got)
	if !approx(m["swap_in_pages_per_sec"].V, 30) || !approx(m["swap_out_pages_per_sec"].V, 6) {
		t.Fatalf("swap tezligi noto'g'ri: %+v %+v", m["swap_in_pages_per_sec"], m["swap_out_pages_per_sec"])
	}

	write(root, "pswpin 5\npswpout 5\n") // reboot: hisoblagich kamaydi
	got, _ = s.Collect(context.Background(), t0.Add(20*time.Second))
	if _, ok := byName(got)["swap_in_pages_per_sec"]; ok {
		t.Fatal("hisoblagich kamayganda manfiy tezlik chiqmasligi kerak")
	}
}

func TestProcState(t *testing.T) {
	for in, want := range map[string]byte{
		"5 (a) R 1":      'R',
		"6 (a b) c) Z 1": 'Z',
		"7 ()) S 1":      'S',
		"garbage":        0,
		"8 (x)":          0,
	} {
		if got := procState([]byte(in)); got != want {
			t.Errorf("procState(%q) = %q, kutilgan %q", in, got, want)
		}
	}
}

func TestDiskInodes(t *testing.T) {
	root := writeProc(t, map[string]string{"mounts": "/dev/sda1 / ext4 rw 0 0\n/dev/sdb1 /data btrfs rw 0 0\n"})
	stat := func(mp string) (FsStat, error) {
		if mp == "/data" {
			return FsStat{BlockSize: 4096, Blocks: 100, Bfree: 50, Bavail: 50}, nil // inode hisoblamaydi
		}
		return FsStat{BlockSize: 4096, Blocks: 1000, Bfree: 500, Bavail: 500, Files: 1000, Ffree: 250}, nil
	}
	got, err := NewDisk(root, nil, stat).Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m[`fs_inodes_used_percent{device=/dev/sda1,fstype=ext4,mount=/}`]; !approx(v.V, 75) {
		t.Fatalf("inode foizi: %+v ", v)
	}
	for k := range m {
		if len(k) > 9 && k[:9] == "fs_inodes" && strings.Contains(k, "/data") {
			t.Fatalf("inode hisoblamaydigan fayl tizimi uchun namuna bo'lmasligi kerak: %s", k)
		}
	}
}

func TestDiskIORatesFiltersAndReset(t *testing.T) {
	// maydonlar: major minor nom reads rmerged rsect rms writes wmerged wsect wms inflight ioticks weighted
	line := func(name string, r, rs, rms, w, ws, wms, io int) string {
		return "8 0 " + name + " " + strconv.Itoa(r) + " 0 " + strconv.Itoa(rs) + " " + strconv.Itoa(rms) + " " + strconv.Itoa(w) + " 0 " + strconv.Itoa(ws) + " " + strconv.Itoa(wms) + " 0 " + strconv.Itoa(io) + " 0\n"
	}
	a := line("sda", 100, 2000, 500, 50, 1000, 250, 400) +
		line("sda1", 90, 1800, 450, 40, 800, 200, 300) + // bo'lim: hisoblanmaydi
		line("loop0", 5, 10, 1, 0, 0, 0, 1) +
		line("dm-0", 5, 10, 1, 0, 0, 0, 1) +
		line("nvme0n1", 10, 100, 10, 10, 100, 10, 20)
	root := writeProc(t, map[string]string{"diskstats": a})
	d := NewDiskIO(root)
	t0 := time.Unix(2_000_000, 0)
	if got, _ := d.Collect(context.Background(), t0); len(got) != 0 {
		t.Fatalf("birinchi o'lchovda namuna bo'lmasligi kerak: %d ta", len(got))
	}

	// 10 s: sda +200 o'qish, +100 yozish, +4000/+2000 sektor, +1000/+500 ms, io_ticks +5000 ms (50%)
	b := line("sda", 300, 6000, 1500, 150, 3000, 750, 5400) + line("sda1", 90, 1800, 450, 40, 800, 200, 300) +
		line("nvme0n1", 10, 100, 10, 10, 100, 10, 20)
	if err := os.WriteFile(filepath.Join(root, "diskstats"), []byte(b), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := d.Collect(context.Background(), t0.Add(10*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	check := func(key string, want float64) {
		t.Helper()
		if v, ok := m[key]; !ok || !approx(v.V, want) {
			t.Errorf("%s = %+v, kutilgan %v", key, v, want)
		}
	}
	check("disk_read_bytes_per_sec{device=sda}", 4000*512/10.0)
	check("disk_write_bytes_per_sec{device=sda}", 2000*512/10.0)
	check("disk_read_iops{device=sda}", 20)
	check("disk_write_iops{device=sda}", 10)
	check("disk_io_util_percent{device=sda}", 50)
	check("disk_await_ms{device=sda}", (1000.0+500.0)/300.0)
	check("disk_read_iops{device=nvme0n1}", 0) // faol emas qurilma ham 0 sifatida ko'rinadi
	for k := range m {
		if strings.Contains(k, "sda1") || strings.Contains(k, "loop") || strings.Contains(k, "dm-") {
			t.Errorf("bo'lim/virtual qurilma hisoblanmasligi kerak: %s", k)
		}
	}

	// reboot: hisoblagich kamaydi -> shu qurilma tashlanadi, manfiy tezlik yo'q
	c := line("sda", 5, 10, 1, 5, 10, 1, 1)
	if err := os.WriteFile(filepath.Join(root, "diskstats"), []byte(c), 0o600); err != nil {
		t.Fatal(err)
	}
	got, _ = d.Collect(context.Background(), t0.Add(20*time.Second))
	for _, s := range got {
		if s.V < 0 {
			t.Fatalf("manfiy qiymat: %+v", s)
		}
	}
}

func TestDiskIONoBlockDevicesIsNotAnError(t *testing.T) {
	root := writeProc(t, map[string]string{"diskstats": "7 0 loop0 1 0 1 1 0 0 0 0 0 0 0\n"})
	got, err := NewDiskIO(root).Collect(context.Background(), time.Now())
	if err != nil || len(got) != 0 {
		t.Fatalf("xato yoki namuna bo'lmasligi kerak: %v %d", err, len(got))
	}
}

func TestRebootFlagAndKernel(t *testing.T) {
	dir := t.TempDir()
	proc := filepath.Join(dir, "proc")
	boot := filepath.Join(dir, "boot")
	for _, p := range []string{filepath.Join(proc, "sys/kernel"), boot} {
		if err := os.MkdirAll(p, 0o750); err != nil {
			t.Fatal(err)
		}
	}
	write := func(p, body string) {
		if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	write(filepath.Join(proc, "sys/kernel/osrelease"), "6.8.0-139-generic\n")
	write(filepath.Join(boot, "vmlinuz-6.8.0-139-generic"), "")
	flag := filepath.Join(dir, "reboot-required")
	now := time.Now()

	// hammasi joyida: reboot kerak emas
	m := byName(collectOK(t, NewReboot(proc, flag, boot), now))
	if m["reboot_required"].V != 0 || m["kernel_reboot_pending"].V != 0 || m["reboot_required_age_seconds"].V != 0 {
		t.Fatalf("toza holat noto'g'ri: %+v", m)
	}

	// yangi kernel o'rnatilgan (9 raqamli qismi bilan ham to'g'ri solishtiriladi: 147 > 139, 1000 > 139)
	write(filepath.Join(boot, "vmlinuz-6.8.0-147-generic"), "")
	write(flag, "*** System restart required ***")
	old := now.Add(-3 * 24 * time.Hour)
	if err := os.Chtimes(flag, old, old); err != nil {
		t.Fatal(err)
	}
	m = byName(collectOK(t, NewReboot(proc, flag, boot), now))
	if m["reboot_required"].V != 1 || m["kernel_reboot_pending"].V != 1 {
		t.Fatalf("reboot belgilari yo'q: %+v", m)
	}
	if !approx(m["reboot_required_age_seconds"].V, 3*86400) {
		t.Fatalf("yoshi: %v", m["reboot_required_age_seconds"].V)
	}

	// /boot o'qib bo'lmasa yoki bo'sh bo'lsa noto'g'ri signal bermaydi
	m = byName(collectOK(t, NewReboot(proc, flag, filepath.Join(dir, "yoq")), now))
	if m["kernel_reboot_pending"].V != 0 {
		t.Fatal("kernel noma'lum bo'lsa belgi qo'yilmasligi kerak")
	}
}

func collectOK(t *testing.T, c Collector, now time.Time) []metric.Sample {
	t.Helper()
	got, err := c.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	return got
}
