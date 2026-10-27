package config

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestParseMinimalAppliesDefaults(t *testing.T) {
	cfg, err := Parse([]byte("core:\n  url: https://nazoratchi.example.uz\n"))
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Collectors.System.Interval != 15*time.Second || cfg.Queue.MaxBytes != 20<<20 {
		t.Fatalf("standart qiymatlar qo'llanmadi: %+v", cfg)
	}
	if cfg.Core.TokenFile != DefaultTokenFile || cfg.Core.Timeout != 10*time.Second {
		t.Fatalf("core standartlari: %+v", cfg.Core)
	}
}

func TestParseFullTZSample(t *testing.T) {
	const sample = `
core:
  url: https://nazoratchi.example.uz
  ca_file: ""
  timeout: 10s
host:
  name: ""
collectors:
  system:  { enabled: true,  interval: 15s }
  disk:    { enabled: true,  interval: 30s, ignore_fstypes: [tmpfs, overlay, squashfs, devtmpfs] }
  diskio:  { enabled: true,  interval: 15s }
  net:     { enabled: true,  interval: 15s, ignore_ifaces: ["lo", "veth*", "br-*", "docker0"] }
  docker:
    enabled: true
    interval: 30s
    endpoint: tcp://127.0.0.1:2375
    max_containers: 100
  systemd:
    enabled: true
    interval: 30s
    units: [nginx, docker, cron, ssh, avlo-contact]
  backup:
    enabled: true
    interval: 300s
    root: /opt/applications/backups
    appctl_conf: /opt/applications/appctl.conf
  certs:
    enabled: true
    interval: 6h
    globs: ["/etc/letsencrypt/live/*/cert.pem"]
  ssh:     { enabled: true, interval: 5m }
  apt:     { enabled: true, interval: 24h }
queue:
  dir: /var/lib/nazoratchi/queue
  max_bytes: 20971520
  max_age: 15m
log:
  level: info
`
	cfg, err := Parse([]byte(sample))
	if err != nil {
		t.Fatalf("TZ 7.6 namunasi o'qilishi kerak: %v", err)
	}
	if cfg.Collectors.Certs.Interval != 6*time.Hour || cfg.Collectors.Systemd.Units[0] != "nginx" {
		t.Fatalf("qiymatlar noto'g'ri: %+v", cfg.Collectors)
	}
}

func TestParseRejectsBadInput(t *testing.T) {
	cases := map[string]struct{ yaml, want string }{
		"url yo'q":           {"log:\n  level: info\n", "core.url"},
		"http tashqi":        {"core:\n  url: http://nazoratchi.example.uz\n", "faqat localhost"},
		"ftp":                {"core:\n  url: ftp://x\n", "https"},
		"noma'lum kalit":     {"core:\n  url: https://x.uz\n  urll: 1\n", "urll"},
		"system interval":    {"core:\n  url: https://x.uz\ncollectors:\n  system: {interval: 1s}\n", "collectors.system.interval"},
		"disk interval":      {"core:\n  url: https://x.uz\ncollectors:\n  disk: {interval: 1s}\n", "collectors.disk.interval"},
		"queue kichik":       {"core:\n  url: https://x.uz\nqueue:\n  max_bytes: 10\n", "queue.max_bytes"},
		"log darajasi":       {"core:\n  url: https://x.uz\nlog:\n  level: loud\n", "log.level"},
		"timeout":            {"core:\n  url: https://x.uz\n  timeout: 5m\n", "core.timeout"},
		"yaml buzuq":         {"core: [\n", "sozlama noto'g'ri"},
		"interval formati":   {"core:\n  url: https://x.uz\ncollectors:\n  system: {interval: tez}\n", "sozlama noto'g'ri"},
		"unit nomi --all":    {"core:\n  url: https://x.uz\ncollectors:\n  systemd: {units: [nginx, \"--all\"]}\n", "collectors.systemd.units"},
		"unit nomi bo'shliq": {"core:\n  url: https://x.uz\ncollectors:\n  systemd: {units: [\"a b\"]}\n", "yaroqsiz unit nomi"},
	}
	for name, c := range cases {
		_, err := Parse([]byte(c.yaml))
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("%s: %q xato kutilgan, olindi: %v", name, c.want, err)
		}
	}
}

func TestLoopbackHTTPAllowed(t *testing.T) {
	for _, u := range []string{"http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"} {
		if _, err := Parse([]byte("core:\n  url: " + u + "\n")); err != nil {
			t.Errorf("%s ruxsat etilishi kerak: %v", u, err)
		}
	}
}

func TestValidateReportsAllErrorsAtOnce(t *testing.T) {
	_, err := Parse([]byte("core:\n  url: http://x.uz\nlog:\n  level: x\nqueue:\n  max_age: 1s\n"))
	if err == nil {
		t.Fatal("xato kutilgan")
	}
	for _, want := range []string{"core.url", "log.level", "queue.max_age"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("%q xabarda yo'q: %v", want, err)
		}
	}
}

func TestExampleConfigIsValid(t *testing.T) {
	data, err := os.ReadFile("../../agent.example.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Parse(data); err != nil {
		t.Fatalf("agent.example.yaml yaroqsiz: %v", err)
	}
}

func TestDefaultsForSystemdAndBackup(t *testing.T) {
	cfg := Default()
	if cfg.Collectors.Systemd.HeartbeatsDir != "/var/lib/nazoratchi/heartbeats" || cfg.Collectors.Systemd.Interval != 30*time.Second {
		t.Fatalf("systemd standartlari: %+v", cfg.Collectors.Systemd)
	}
	b := cfg.Collectors.Backup
	if b.Root != "/opt/applications/backups" || b.AppctlConf != "/opt/applications/appctl.conf" || b.Interval != 300*time.Second {
		t.Fatalf("backup standartlari: %+v", b)
	}
}
