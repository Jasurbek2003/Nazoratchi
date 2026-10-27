// Package config — `agent.yaml` ni o'qish va tekshirish (TZ 7.6). Noma'lum kalit yoki yaroqsiz
// qiymat bo'lsa agent ishga tushmaydi va aniq xabar beradi.
package config

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"os"
	"strings"
	"time"

	"nazoratchi/agent/internal/collector"

	"gopkg.in/yaml.v3"
)

const (
	DefaultPath      = "/etc/nazoratchi/agent.yaml"
	DefaultTokenFile = "/etc/nazoratchi/token"
)

type Config struct {
	Core       Core       `yaml:"core"`
	Host       Host       `yaml:"host"`
	Collectors Collectors `yaml:"collectors"`
	Queue      Queue      `yaml:"queue"`
	Log        Log        `yaml:"log"`
}

type Core struct {
	URL       string        `yaml:"url"`
	CAFile    string        `yaml:"ca_file"`
	Timeout   time.Duration `yaml:"timeout"`
	TokenFile string        `yaml:"token_file"`
}

type Host struct {
	Name string `yaml:"name"`
}

// Collector — barcha kollektorlar uchun umumiy sozlama; har biri o'ziga tegishli maydonlarni o'qiydi.
type Collector struct {
	Enabled       bool          `yaml:"enabled"`
	Interval      time.Duration `yaml:"interval"`
	IgnoreFSTypes []string      `yaml:"ignore_fstypes"`
	IgnoreIfaces  []string      `yaml:"ignore_ifaces"`
	Endpoint      string        `yaml:"endpoint"`
	MaxContainers int           `yaml:"max_containers"`
	Units         []string      `yaml:"units"`
	Root          string        `yaml:"root"`
	AppctlConf    string        `yaml:"appctl_conf"`
	Globs         []string      `yaml:"globs"`
	HeartbeatsDir string        `yaml:"heartbeats_dir"`
}

type Collectors struct {
	System  Collector `yaml:"system"`
	Disk    Collector `yaml:"disk"`
	DiskIO  Collector `yaml:"diskio"`
	Net     Collector `yaml:"net"`
	Docker  Collector `yaml:"docker"`
	Systemd Collector `yaml:"systemd"`
	Backup  Collector `yaml:"backup"`
	Certs   Collector `yaml:"certs"`
	SSH     Collector `yaml:"ssh"`
	Apt     Collector `yaml:"apt"`
}

type Queue struct {
	Dir      string        `yaml:"dir"`
	MaxBytes int64         `yaml:"max_bytes"`
	MaxAge   time.Duration `yaml:"max_age"`
}

type Log struct {
	Level string `yaml:"level"`
}

// Default TZ 7.6 dagi standart qiymatlar. Hali amalga oshirilmagan kollektorlar (diskio, docker, ...)
// sozlanishi mumkin, lekin agent ularni ishga tushirmaydi (ogohlantirish beradi).
func Default() *Config {
	return &Config{
		Core: Core{Timeout: 10 * time.Second, TokenFile: DefaultTokenFile},
		Collectors: Collectors{
			System:  Collector{Enabled: true, Interval: 15 * time.Second},
			Disk:    Collector{Enabled: true, Interval: 30 * time.Second},
			DiskIO:  Collector{Enabled: true, Interval: 15 * time.Second},
			Net:     Collector{Enabled: true, Interval: 15 * time.Second, IgnoreIfaces: []string{"lo", "veth*", "br-*", "docker0"}},
			Docker:  Collector{Enabled: true, Interval: 30 * time.Second, Endpoint: "tcp://127.0.0.1:2375", MaxContainers: 100},
			Systemd: Collector{Enabled: true, Interval: 30 * time.Second, HeartbeatsDir: collector.DefaultHeartbeatsDir},
			Backup:  Collector{Enabled: true, Interval: 300 * time.Second, Root: collector.DefaultBackupRoot, AppctlConf: collector.DefaultAppctlConf},
			Certs:   Collector{Enabled: true, Interval: 6 * time.Hour},
			SSH:     Collector{Enabled: true, Interval: 5 * time.Minute},
			Apt:     Collector{Enabled: true, Interval: 24 * time.Hour},
		},
		Queue: Queue{Dir: "/var/lib/nazoratchi/queue", MaxBytes: 20 << 20, MaxAge: 15 * time.Minute},
		Log:   Log{Level: "info"},
	}
}

// Load faylni o'qiydi (yo'q bo'lsa xato), standart qiymatlar ustiga qo'yadi va tekshiradi.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("sozlama fayli o'qilmadi: %w", err)
	}
	return Parse(data)
}

func Parse(data []byte) (*Config, error) {
	cfg := Default()
	dec := yaml.NewDecoder(bytes.NewReader(data))
	dec.KnownFields(true)
	if err := dec.Decode(cfg); err != nil && !errors.Is(err, io.EOF) {
		return nil, fmt.Errorf("sozlama noto'g'ri: %w", err)
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// Validate barcha xatolarni birdan qaytaradi (operator bir urinishda hammasini tuzatsin).
func (c *Config) Validate() error {
	var errs []error
	bad := func(format string, a ...any) { errs = append(errs, fmt.Errorf(format, a...)) }

	if err := ValidateCoreURL(c.Core.URL); err != nil {
		bad("core.url: %v", err)
	}
	if c.Core.Timeout < time.Second || c.Core.Timeout > time.Minute {
		bad("core.timeout 1s dan 60s gacha bo'lishi kerak")
	}
	if c.Core.TokenFile == "" {
		bad("core.token_file bo'sh bo'lmasligi kerak")
	}
	sys := c.Collectors.System.Interval
	if sys < 5*time.Second || sys > 60*time.Second {
		bad("collectors.system.interval 5s dan 60s gacha bo'lishi kerak")
	}
	for name, col := range c.Collectors.All() {
		if name == "system" {
			continue
		}
		if col.Interval < 5*time.Second || col.Interval > 48*time.Hour {
			bad("collectors.%s.interval 5s dan 48h gacha bo'lishi kerak", name)
		}
	}
	for _, u := range c.Collectors.Systemd.Units {
		if !collector.ValidUnitName(u) {
			bad("collectors.systemd.units: yaroqsiz unit nomi %q", u)
		}
	}
	if c.Queue.Dir == "" {
		bad("queue.dir bo'sh bo'lmasligi kerak")
	}
	if c.Queue.MaxBytes < 1<<20 || c.Queue.MaxBytes > 1<<30 {
		bad("queue.max_bytes 1 MB dan 1 GB gacha bo'lishi kerak")
	}
	if c.Queue.MaxAge < time.Minute {
		bad("queue.max_age kamida 1m bo'lishi kerak")
	}
	switch strings.ToLower(c.Log.Level) {
	case "debug", "info", "warn", "error":
	default:
		bad("log.level debug, info, warn yoki error bo'lishi kerak")
	}
	return errors.Join(errs...)
}

// All kollektor nomi -> sozlama (tekshirish va ro'yxat uchun).
func (c Collectors) All() map[string]Collector {
	return map[string]Collector{
		"system": c.System, "disk": c.Disk, "diskio": c.DiskIO, "net": c.Net, "docker": c.Docker,
		"systemd": c.Systemd, "backup": c.Backup, "certs": c.Certs, "ssh": c.SSH, "apt": c.Apt,
	}
}

// ValidateCoreURL: TLS majburiy (TZ 14.7); faqat loopback uchun (dev) oddiy http ruxsat etiladi.
func ValidateCoreURL(raw string) error {
	if raw == "" {
		return errors.New("majburiy")
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return errors.New("yaroqli URL emas")
	}
	switch u.Scheme {
	case "https":
		return nil
	case "http":
		host := u.Hostname()
		if host == "localhost" {
			return nil
		}
		if ip := net.ParseIP(host); ip != nil && ip.IsLoopback() {
			return nil
		}
		return errors.New("http faqat localhost uchun ruxsat etiladi, https ishlating")
	default:
		return errors.New("sxema https bo'lishi kerak")
	}
}
