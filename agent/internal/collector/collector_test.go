package collector

import (
	"context"
	"errors"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"testing"
	"time"

	"nazoratchi/agent/internal/metric"
)

var nameRe = regexp.MustCompile(`^[a-z][a-z0-9_]{0,99}$`)

func writeProc(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	for name, body := range files {
		p := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(p), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func byName(samples []metric.Sample) map[string]metric.Sample {
	m := map[string]metric.Sample{}
	for _, s := range samples {
		m[s.SeriesKey()] = s
	}
	return m
}

func approx(a, b float64) bool { return math.Abs(a-b) < 1e-6 }

const statA = `cpu  1000 0 500 8000 500 0 0 0 0 0
cpu0 500 0 250 4000 250 0 0 0 0 0
cpu1 500 0 250 4000 250 0 0 0 0 0
btime 1761000000
`

// idle +800, iowait +200, user +600, system +400 -> jami 2000, band = 100 - 1000/2000*100 = 50%
const statB = `cpu  1600 0 900 8800 700 0 0 0 0 0
cpu0 800 0 450 4400 350 0 0 0 0 0
cpu1 800 0 450 4400 350 0 0 0 0 0
btime 1761000000
`

const meminfo = `MemTotal:        8000000 kB
MemFree:         1000000 kB
MemAvailable:    2000000 kB
SwapTotal:       1000000 kB
SwapFree:         750000 kB
`

func TestSystemCPUNeedsTwoReadings(t *testing.T) {
	root := writeProc(t, map[string]string{
		"stat": statA, "loadavg": "1.00 0.50 0.25 1/100 1\n", "meminfo": meminfo, "uptime": "100.5 50.0\n",
	})
	s := NewSystem(root)
	now := time.UnixMilli(1761125700000)

	first, err := s.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := byName(first)["cpu_busy_percent"]; ok {
		t.Fatal("birinchi o'lchovda cpu foizi bo'lmasligi kerak")
	}

	if err := os.WriteFile(filepath.Join(root, "stat"), []byte(statB), 0o600); err != nil {
		t.Fatal(err)
	}
	second, err := s.Collect(context.Background(), now.Add(15*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	m := byName(second)
	if got := m["cpu_busy_percent"].V; !approx(got, 50) {
		t.Fatalf("cpu_busy_percent = %v, 50 kutilgan edi", got)
	}
	if got := m["cpu_usage_percent{mode=user}"].V; !approx(got, 30) {
		t.Fatalf("user = %v, 30 kutilgan edi", got)
	}
	if got := m["cpu_usage_percent{mode=iowait}"].V; !approx(got, 10) {
		t.Fatalf("iowait = %v", got)
	}
	if got := m["load_per_core_1m"].V; !approx(got, 0.5) { // 1.00 / 2 yadro
		t.Fatalf("load_per_core_1m = %v", got)
	}
	if m["boot_time_seconds"].V != 1761000000 || m["uptime_seconds"].V != 100.5 {
		t.Fatal("boot_time/uptime noto'g'ri")
	}
}

func TestSystemCPUCounterResetIsSkipped(t *testing.T) {
	root := writeProc(t, map[string]string{"stat": statB, "loadavg": "0 0 0 1/1 1", "meminfo": meminfo, "uptime": "1 1"})
	s := NewSystem(root)
	_, _ = s.Collect(context.Background(), time.Now())
	if err := os.WriteFile(filepath.Join(root, "stat"), []byte(statA), 0o600); err != nil { // kamaydi
		t.Fatal(err)
	}
	got, err := s.Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := byName(got)["cpu_busy_percent"]; ok {
		t.Fatal("hisoblagich qayta boshlanganda foiz chiqmasligi kerak")
	}
}

func TestSystemMemory(t *testing.T) {
	root := writeProc(t, map[string]string{"stat": statA, "loadavg": "0 0 0 1/1 1", "meminfo": meminfo, "uptime": "1 1"})
	got, err := NewSystem(root).Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if !approx(m["mem_total_bytes"].V, 8000000*1024) || !approx(m["mem_used_bytes"].V, 6000000*1024) {
		t.Fatalf("xotira baytlari noto'g'ri: %+v", m["mem_used_bytes"])
	}
	if !approx(m["mem_used_percent"].V, 75) {
		t.Fatalf("mem_used_percent = %v", m["mem_used_percent"].V)
	}
	if !approx(m["swap_used_percent"].V, 25) {
		t.Fatalf("swap_used_percent = %v", m["swap_used_percent"].V)
	}
}

func TestSystemSwapAbsentGivesZeroPercent(t *testing.T) {
	root := writeProc(t, map[string]string{
		"stat": statA, "loadavg": "0 0 0 1/1 1", "uptime": "1 1",
		"meminfo": "MemTotal: 1000 kB\nMemAvailable: 500 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
	})
	got, _ := NewSystem(root).Collect(context.Background(), time.Now())
	if v := byName(got)["swap_used_percent"].V; v != 0 {
		t.Fatalf("swap yo'q bo'lsa 0 kutilgan, %v", v)
	}
}

func TestSystemPartialFailureKeepsOtherSamples(t *testing.T) {
	root := writeProc(t, map[string]string{"stat": statA, "loadavg": "0.1 0.2 0.3 1/1 1", "uptime": "9 9"}) // meminfo yo'q
	got, err := NewSystem(root).Collect(context.Background(), time.Now())
	if err == nil {
		t.Fatal("meminfo yo'qligi xato berishi kerak")
	}
	if _, ok := byName(got)["load1"]; !ok {
		t.Fatal("qolgan namunalar saqlanishi kerak")
	}
}

func TestAllSampleNamesMatchProtocol(t *testing.T) {
	root := writeProc(t, map[string]string{"stat": statA, "loadavg": "0 0 0 1/1 1", "meminfo": meminfo, "uptime": "1 1"})
	s := NewSystem(root)
	_, _ = s.Collect(context.Background(), time.Now())
	_ = os.WriteFile(filepath.Join(root, "stat"), []byte(statB), 0o600)
	got, _ := s.Collect(context.Background(), time.Now())
	for _, sm := range got {
		if !nameRe.MatchString(sm.N) || !sm.Finite() {
			t.Fatalf("yaroqsiz namuna: %+v", sm)
		}
		if len(sm.N) > 0 && regexp.MustCompile(`_percent$`).MatchString(sm.N) && (sm.V < 0 || sm.V > 100) {
			t.Fatalf("foiz diapazondan tashqarida: %+v", sm)
		}
	}
}

const mounts = `/dev/sda1 / ext4 rw,relatime 0 0
proc /proc proc rw,nosuid 0 0
tmpfs /run tmpfs rw 0 0
overlay /var/lib/docker/overlay2/x/merged overlay rw 0 0
/dev/sda1 /var/lib/docker/vol ext4 rw 0 0
/dev/sdb1 /mnt/my\040data ext4 ro,relatime 0 0
/dev/sdc1 /broken ext4 rw 0 0
`

func TestDiskFiltersDedupesAndReportsReadonly(t *testing.T) {
	root := writeProc(t, map[string]string{"mounts": mounts})
	stat := func(p string) (FsStat, error) {
		if p == "/broken" {
			return FsStat{}, errors.New("I/O xato")
		}
		return FsStat{BlockSize: 4096, Blocks: 1000, Bfree: 400, Bavail: 300}, nil
	}
	got, err := NewDisk(root, nil, stat).Collect(context.Background(), time.Now())
	if err == nil {
		t.Fatal("/broken uchun xato kutilgan edi")
	}
	m := byName(got)
	root1 := "fs_used_percent{device=/dev/sda1,fstype=ext4,mount=/}"
	// used = (1000-400)*4096, avail = 300*4096 -> 600/900 = 66.67%
	if v := m[root1].V; !approx(v, 100*600.0/900.0) {
		t.Fatalf("fs_used_percent = %v", v)
	}
	if v := m["fs_total_bytes{device=/dev/sda1,fstype=ext4,mount=/}"].V; v != 1000*4096 {
		t.Fatalf("fs_total_bytes = %v", v)
	}
	if _, ok := m["fs_total_bytes{device=/dev/sda1,fstype=ext4,mount=/var/lib/docker/vol}"]; ok {
		t.Fatal("bir qurilmaning ikkinchi ulanishi qaytarilmasligi kerak")
	}
	if _, ok := m["fs_total_bytes{device=proc,fstype=proc,mount=/proc}"]; ok {
		t.Fatal("proc ko'rsatilmasligi kerak")
	}
	if v, ok := m["fs_readonly{device=/dev/sdb1,mount=/mnt/my data}"]; !ok || v.V != 1 {
		t.Fatalf("bo'shliqli yo'l va ro'yxat faqat-o'qish: %+v", v)
	}
	if v := m["fs_readonly{device=/dev/sda1,mount=/}"].V; v != 0 {
		t.Fatal("rw uchun 0 kutilgan")
	}
	for _, s := range got {
		for k, v := range s.L {
			if len(v) > 200 {
				t.Fatalf("belgi %s juda uzun", k)
			}
		}
	}
}

func TestDiskIgnoreFromConfig(t *testing.T) {
	root := writeProc(t, map[string]string{"mounts": "/dev/sda1 / ext4 rw 0 0\n/dev/sdb1 /x xfs rw 0 0\n"})
	stat := func(string) (FsStat, error) { return FsStat{BlockSize: 1, Blocks: 10, Bfree: 5, Bavail: 5}, nil }
	got, _ := NewDisk(root, []string{"xfs"}, stat).Collect(context.Background(), time.Now())
	for _, s := range got {
		if s.L["fstype"] == "xfs" {
			t.Fatal("sozlamadagi fstype e'tiborsiz qoldirilmadi")
		}
	}
}

func TestUnescapeMount(t *testing.T) {
	cases := map[string]string{
		`/mnt/a\040b`: "/mnt/a b",
		`/plain`:      "/plain",
		`/x\134y`:     `/x\y`,
		`/bad\9zz`:    `/bad\9zz`,
		`end\04`:      `end\04`,
	}
	for in, want := range cases {
		if got := unescapeMount(in); got != want {
			t.Errorf("unescapeMount(%q) = %q, %q kutilgan", in, got, want)
		}
	}
}

const netDev1 = `Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 10000 100 0 0 0 0 0 0 5000 50 0 0 0 0 0 0
 veth1: 99 1 0 0 0 0 0 0 99 1 0 0 0 0 0 0
`

const netDev2 = `Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 2000 20 0 0 0 0 0 0 2000 20 0 0 0 0 0 0
  eth0: 40000 200 0 0 0 0 0 0 20000 80 0 0 0 0 0 0
 veth1: 199 2 0 0 0 0 0 0 199 2 0 0 0 0 0 0
`

func TestNetRates(t *testing.T) {
	root := writeProc(t, map[string]string{"net/dev": netDev1})
	n := NewNet(root, []string{"lo", "veth*"})
	t0 := time.UnixMilli(1761125700000)

	first, err := n.Collect(context.Background(), t0)
	if err != nil || len(first) != 0 {
		t.Fatalf("birinchi o'lchovda tezlik bo'lmasligi kerak: %v %v", first, err)
	}
	if err := os.WriteFile(filepath.Join(root, "net/dev"), []byte(netDev2), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := n.Collect(context.Background(), t0.Add(15*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m["net_rx_bytes_per_sec{iface=eth0}"].V; !approx(v, 30000.0/15) {
		t.Fatalf("rx = %v", v)
	}
	if v := m["net_tx_bytes_per_sec{iface=eth0}"].V; !approx(v, 15000.0/15) {
		t.Fatalf("tx = %v", v)
	}
	if len(got) != 2 {
		t.Fatalf("lo va veth* yashirilishi kerak, %d namuna", len(got))
	}
}

func TestNetCounterResetNeverNegative(t *testing.T) {
	root := writeProc(t, map[string]string{"net/dev": netDev2})
	n := NewNet(root, nil)
	t0 := time.Now()
	_, _ = n.Collect(context.Background(), t0)
	_ = os.WriteFile(filepath.Join(root, "net/dev"), []byte(netDev1), 0o600) // kamaydi
	got, _ := n.Collect(context.Background(), t0.Add(time.Second))
	for _, s := range got {
		if s.V < 0 {
			t.Fatalf("manfiy tezlik: %+v", s)
		}
	}
}

func TestNetBrokenLineKeepsOthers(t *testing.T) {
	root := writeProc(t, map[string]string{"net/dev": "  eth0: 100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0\n bad: 1 2\n"})
	n := NewNet(root, nil)
	_, err := n.Collect(context.Background(), time.Now())
	if err == nil {
		t.Fatal("buzuq qator xato bo'lishi kerak")
	}
	if _, ok := n.prev["eth0"]; !ok {
		t.Fatal("yaroqli interfeys saqlanishi kerak")
	}
}

func TestRealProcSmoke(t *testing.T) {
	if _, err := os.Stat("/proc/stat"); err != nil {
		t.Skip("Linux emas")
	}
	for _, c := range []Collector{NewSystem("/proc"), NewDisk("/proc", nil, nil), NewNet("/proc", []string{"lo"})} {
		for i := 0; i < 2; i++ {
			got, err := c.Collect(context.Background(), time.Now().Add(time.Duration(i)*time.Second))
			if err != nil {
				t.Logf("%s: %v", c.Name(), err) // konteynerda ba'zi fayl tizimlari ochilmasligi mumkin
			}
			for _, s := range got {
				if !nameRe.MatchString(s.N) || !s.Finite() {
					t.Fatalf("%s: yaroqsiz namuna %+v", c.Name(), s)
				}
			}
		}
	}
}
