package facts

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func write(t *testing.T, root, name, body string) {
	t.Helper()
	p := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(p), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestCollect(t *testing.T) {
	root := t.TempDir()
	write(t, root, "proc/sys/kernel/osrelease", "6.8.0-139-generic\n")
	write(t, root, "proc/sys/kernel/random/boot_id", "abc-123\n")
	write(t, root, "proc/cpuinfo", "processor\t: 0\nmodel name\t: AMD EPYC 7543\n\nprocessor\t: 1\nmodel name\t: AMD EPYC 7543\n")
	write(t, root, "proc/meminfo", "MemTotal:        8126088 kB\nMemFree: 1 kB\n")
	write(t, root, "os-release", "NAME=\"Ubuntu\"\nPRETTY_NAME=\"Ubuntu 24.04.3 LTS\"\n")
	write(t, root, "boot/vmlinuz-6.8.0-9-generic", "")
	write(t, root, "boot/vmlinuz-6.8.0-147-generic", "")
	write(t, root, "boot/vmlinuz-6.8.0-139-generic", "")

	f := Source{
		Proc: filepath.Join(root, "proc"), OSRelease: filepath.Join(root, "os-release"),
		BootDir: filepath.Join(root, "boot"), HostName: func() (string, error) { return "vmi3679093", nil },
	}.Collect()

	want := map[string]any{
		"hostname": "vmi3679093", "os": "Ubuntu 24.04.3 LTS", "kernel_running": "6.8.0-139-generic",
		"kernel_latest_installed": "6.8.0-147-generic", "boot_id": "abc-123",
		"cpu_model": "AMD EPYC 7543", "cpu_count": 2, "mem_total_bytes": int64(8126088 * 1024),
	}
	for k, v := range want {
		if f[k] != v {
			t.Errorf("%s = %v (%T), %v kutilgan", k, f[k], f[k], v)
		}
	}
	if f["arch"] == "" || f["arch"] == nil {
		t.Error("arch yo'q")
	}
}

func TestNameOverrideAndMissingFiles(t *testing.T) {
	f := Source{
		Proc: "/yoq", OSRelease: "/yoq", BootDir: "/yoq",
		HostName: func() (string, error) { return "real", nil }, NameConfig: "custom",
	}.Collect()
	if f["hostname"] != "custom" {
		t.Fatalf("hostname = %v", f["hostname"])
	}
	for _, k := range []string{"os", "kernel_running", "kernel_latest_installed", "cpu_count"} {
		if _, ok := f[k]; ok {
			t.Errorf("%s fayl yo'q bo'lsa tushirib qoldirilishi kerak", k)
		}
	}
}

func TestVersionLess(t *testing.T) {
	if !versionLess("6.8.0-9-generic", "6.8.0-147-generic") || versionLess("6.8.0-147-generic", "6.8.0-9-generic") {
		t.Fatal("raqamli solishtirish noto'g'ri")
	}
	if !versionLess("6.8.0-147-generic", "6.10.0-1-generic") {
		t.Fatal("6.8 < 6.10 bo'lishi kerak")
	}
}

func TestBuildTimeAndGoVersionAreReported(t *testing.T) {
	// FR-AGT-011: agent build vaqti, OS va arxitekturani bildiradi (versiya X-Nazoratchi-Agent sarlavhasida).
	src := Source{Proc: t.TempDir(), HostName: func() (string, error) { return "h", nil }, BuildTime: "2026-11-01T10:00:00Z"}
	f := src.Collect()
	if f["agent_build_time"] != "2026-11-01T10:00:00Z" {
		t.Errorf("agent_build_time = %v", f["agent_build_time"])
	}
	if v, _ := f["go_version"].(string); !strings.HasPrefix(v, "go") {
		t.Errorf("go_version = %v", f["go_version"])
	}
	src.BuildTime = ""
	if _, ok := src.Collect()["agent_build_time"]; ok {
		t.Error("build vaqti noma'lum bo'lsa fakt yuborilmasligi kerak")
	}
}
