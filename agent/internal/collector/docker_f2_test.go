package collector

import (
	"context"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func newF2Docker(t *testing.T, cs []fakeContainer, now time.Time) *Docker {
	t.Helper()
	srv := httptest.NewServer(dockerHandler(cs, now))
	t.Cleanup(srv.Close)
	d, err := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 100)
	if err != nil {
		t.Fatal(err)
	}
	return d
}

const lbl = "{container=%s,project=,service=}"

func key(name, container string) string { return name + strings.Replace(lbl, "%s", container, 1) }

func TestDockerMemoryExcludesCacheAndMarksUnlimited(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	const mib = 1 << 20
	cs := []fakeContainer{
		{id: "a", name: "limited", state: "running", memUsage: 600 * mib, inactive: 100 * mib, memLimit: 1024 * mib},
		{id: "b", name: "unlimited", state: "running", memUsage: 300 * mib, memLimit: hostMemTotal},         // limit = xost RAM
		{id: "c", name: "v1unlimited", state: "running", memUsage: 10 * mib, memLimit: 9223372036854771712}, // cgroup v1
		{id: "d", name: "stopped", state: "exited", memUsage: 5 * mib},
	}
	got, err := newF2Docker(t, cs, now).Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m[key("docker_container_mem_bytes", "limited")].V; !approx(v, 500*mib) {
		t.Errorf("mem_bytes keshsiz 500 MiB bo'lishi kerak: %v", v)
	}
	if v := m[key("docker_container_mem_limit_bytes", "limited")].V; !approx(v, 1024*mib) {
		t.Errorf("mem_limit_bytes: %v", v)
	}
	if v := m[key("docker_container_mem_percent", "limited")].V; !approx(v, 100*500.0/1024) {
		t.Errorf("mem_percent: %v", v)
	}
	for _, name := range []string{"unlimited", "v1unlimited"} {
		if v, ok := m[key("docker_container_mem_limit_bytes", name)]; !ok || v.V != 0 {
			t.Errorf("%s: limit 0 (cheksiz) kutilgan: %+v", name, v)
		}
		if _, ok := m[key("docker_container_mem_percent", name)]; ok {
			t.Errorf("%s: limitsiz konteynerda foiz bo'lmasligi kerak", name)
		}
	}
	if _, ok := m[key("docker_container_mem_bytes", "stopped")]; ok {
		t.Error("to'xtagan konteynerda resurs sarfi bo'lmasligi kerak")
	}
}

func TestDockerCPUPercentFromDelta(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	cs := []fakeContainer{{id: "a", name: "busy", state: "running", cpuTotal: 5_000_000_000, cpuSystem: 100_000_000_000}}
	d := newF2Docker(t, cs, now)

	got, _ := d.Collect(context.Background(), now)
	if _, ok := byName(got)[key("docker_container_cpu_percent", "busy")]; ok {
		t.Fatal("birinchi o'lchovda CPU foizi bo'lmasligi kerak")
	}

	// konteyner 1 s CPU sarfladi, tizim 4 s (2 yadro x 2 s): 1/4 x 2 yadro x 100 = 50%
	cs[0].cpuTotal += 1_000_000_000
	cs[0].cpuSystem += 4_000_000_000
	got, _ = d.Collect(context.Background(), now.Add(30*time.Second))
	if v := byName(got)[key("docker_container_cpu_percent", "busy")].V; !approx(v, 50) {
		t.Fatalf("cpu_percent = %v, 50 kutilgan", v)
	}

	// konteyner qayta ishga tushdi: hisoblagich kamaydi, manfiy/yolg'on qiymat chiqmasin
	cs[0].cpuTotal = 100
	cs[0].cpuSystem += 4_000_000_000
	got, _ = d.Collect(context.Background(), now.Add(60*time.Second))
	if _, ok := byName(got)[key("docker_container_cpu_percent", "busy")]; ok {
		t.Fatal("hisoblagich kamayganda CPU foizi chiqmasligi kerak")
	}
}

func TestDockerStatsFailureKeepsOtherMetrics(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	cs := []fakeContainer{
		{id: "a", name: "broken", state: "running", statsFails: true},
		{id: "b", name: "fine", state: "running", memUsage: 1 << 20, memLimit: 1 << 30},
	}
	got, err := newF2Docker(t, cs, now).Collect(context.Background(), now)
	if err == nil || !strings.Contains(err.Error(), "broken stats") {
		t.Fatalf("stats xatosi qaytarilishi kerak: %v", err)
	}
	m := byName(got)
	if _, ok := m[key("docker_container_running", "broken")]; !ok {
		t.Error("stats xatosi F1 metrikalarini yo'qotmasligi kerak")
	}
	if _, ok := m[key("docker_container_mem_bytes", "fine")]; !ok {
		t.Error("boshqa konteyner stats i saqlanishi kerak")
	}
}

func TestDockerPrevCPUDroppedForGoneContainers(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	cs := []fakeContainer{{id: "a", name: "x", state: "running"}, {id: "b", name: "y", state: "running"}}
	d := newF2Docker(t, cs, now)
	_, _ = d.Collect(context.Background(), now)
	if len(d.prevCPU) != 2 {
		t.Fatalf("2 ta o'lchov kutilgan: %d", len(d.prevCPU))
	}
	// "b" ro'yxatdan yo'qoldi (soxta serverning ro'yxati qisqardi)
	cs[1].state = "gone"
	cs[1].id = "zzz-new"
	_, _ = d.Collect(context.Background(), now.Add(time.Minute))
	if _, ok := d.prevCPU["b"]; ok {
		t.Fatal("yo'q bo'lgan konteynerning CPU o'lchovi o'chirilishi kerak")
	}
}

func TestDockerLogBytesSumsRotatedFilesAndIgnoresMissing(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "abc-json.log")
	for name, n := range map[string]int{"abc-json.log": 100, "abc-json.log.1": 50, "other-json.log": 999} {
		if err := os.WriteFile(filepath.Join(dir, name), make([]byte, n), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	now := time.UnixMilli(1761125700000)
	cs := []fakeContainer{
		{id: "a", name: "logging", state: "running", logPath: logPath},
		{id: "b", name: "nolog", state: "running", logPath: filepath.Join(dir, "yoq-json.log")},
		{id: "c", name: "journald", state: "running"}, // LogPath bo'sh (json-file emas)
	}
	got, err := newF2Docker(t, cs, now).Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m[key("docker_container_log_bytes", "logging")].V; v != 150 {
		t.Errorf("log hajmi aylantirilgan fayl bilan 150 bo'lishi kerak: %v", v)
	}
	for _, name := range []string{"nolog", "journald"} {
		if _, ok := m[key("docker_container_log_bytes", name)]; ok {
			t.Errorf("%s: fayl yo'q bo'lsa metrika chiqmasligi kerak", name)
		}
	}
}

func TestDockerSystemDFOncePerTenMinutes(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	d := newF2Docker(t, []fakeContainer{{id: "a", name: "x", state: "running"}}, now)

	got, err := d.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	for name, want := range map[string]float64{
		"docker_images_bytes":     1000,                            // LayersSize: umumiy qatlam ikki marta sanalmaydi
		"docker_containers_bytes": 15, "docker_volumes_bytes": 300, // hajmi noma'lum (-1) volume qo'shilmaydi
		"docker_build_cache_bytes": 42,
	} {
		if s, ok := m[name]; !ok || s.V != want {
			t.Errorf("%s = %+v, %v kutilgan", name, s, want)
		}
	}

	got, _ = d.Collect(context.Background(), now.Add(9*time.Minute))
	if _, ok := byName(got)["docker_images_bytes"]; ok {
		t.Error("10 daqiqadan oldin df qayta so'ralmasligi kerak")
	}
	got, _ = d.Collect(context.Background(), now.Add(11*time.Minute))
	if _, ok := byName(got)["docker_images_bytes"]; !ok {
		t.Error("10 daqiqadan keyin df qayta chiqishi kerak")
	}
}
