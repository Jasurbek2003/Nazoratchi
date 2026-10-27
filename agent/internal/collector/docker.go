package collector

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"

	"nazoratchi/agent/internal/metric"
)

const (
	dockerHealthNone      = 0.0
	dockerHealthHealthy   = 1.0
	dockerHealthUnhealthy = 2.0
	dockerHealthStarting  = 3.0
	maxLabelValue         = 200
	maxDockerBody         = 4 << 20
)

// Docker — konteyner holati (TZ 7.4.4, F1 qismi): ishlayaptimi, qayta ishga tushishlar, ishlash vaqti,
// health, OOM. Faqat GET so'rovlar (docker-socket-proxy orqali yoki `unix://` soket); agent konteynerni
// boshqarmaydi (X-8).
type Docker struct {
	base   string
	client *http.Client
	max    int

	mu       sync.Mutex
	expected map[string]*expectedContainer // TZ 11.5.1: "kutilgan" konteynerlar (xotirada)
}

// expectedContainer — kamida ExpectedAfter uzluksiz ishlagan va RestartPolicy `no` bo'lmagan konteyner.
type expectedContainer struct {
	labels   []string
	lastSeen time.Time
}

const (
	// ExpectedAfter — shuncha uzluksiz `running` bo'lgan konteyner "kutilgan" hisoblanadi.
	ExpectedAfter = time.Hour
	// ForgetMissingAfter — kutilgan konteyner ro'yxatdan shuncha vaqt yo'qolsa, ataylab olib tashlangan deb unutiladi
	// (panelda "kutilgan ro'yxatdan chiqarish" tugmasi — F3).
	ForgetMissingAfter = 10 * time.Minute
)

// NewDocker: endpoint `tcp://127.0.0.1:2375` yoki `unix:///var/run/docker.sock`.
func NewDocker(endpoint string, maxContainers int) (*Docker, error) {
	u, err := url.Parse(endpoint)
	if err != nil {
		return nil, fmt.Errorf("docker endpoint: %w", err)
	}
	d := &Docker{max: maxContainers, expected: map[string]*expectedContainer{}}
	switch u.Scheme {
	case "tcp", "http":
		if u.Host == "" {
			return nil, errors.New("docker endpoint: host yo'q")
		}
		d.base = "http://" + u.Host
		d.client = &http.Client{}
	case "unix":
		path := u.Path
		d.base = "http://docker"
		d.client = &http.Client{Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				var dialer net.Dialer
				return dialer.DialContext(ctx, "unix", path)
			},
		}}
	default:
		return nil, fmt.Errorf("docker endpoint: %q sxemasi qo'llanmaydi (tcp:// yoki unix://)", u.Scheme)
	}
	if d.max <= 0 {
		d.max = 100
	}
	return d, nil
}

func (d *Docker) Name() string { return "docker" }

type dockerListItem struct {
	ID     string            `json:"Id"`
	Names  []string          `json:"Names"`
	State  string            `json:"State"`
	Labels map[string]string `json:"Labels"`
}

type dockerInspect struct {
	RestartCount int `json:"RestartCount"`
	HostConfig   struct {
		RestartPolicy struct {
			Name string `json:"Name"`
		} `json:"RestartPolicy"`
	} `json:"HostConfig"`
	State struct {
		Running    bool   `json:"Running"`
		Restarting bool   `json:"Restarting"`
		OOMKilled  bool   `json:"OOMKilled"`
		StartedAt  string `json:"StartedAt"`
		Health     *struct {
			Status string `json:"Status"`
		} `json:"Health"`
	} `json:"State"`
}

func (d *Docker) get(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, d.base+path, nil)
	if err != nil {
		return err
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("docker API %s: HTTP %d", strings.SplitN(path, "?", 2)[0], resp.StatusCode)
	}
	return json.NewDecoder(io.LimitReader(resp.Body, maxDockerBody)).Decode(out)
}

func trunc(s string) string {
	if len(s) > maxLabelValue {
		return s[:maxLabelValue]
	}
	return s
}

func (d *Docker) Collect(ctx context.Context, now time.Time) ([]metric.Sample, error) {
	var list []dockerListItem
	if err := d.get(ctx, "/containers/json?all=1", &list); err != nil {
		return nil, err
	}
	sort.Slice(list, func(i, j int) bool { return firstName(list[i]) < firstName(list[j]) })
	o := newOut(now)
	running := 0
	for _, c := range list {
		if c.State == "running" {
			running++
		}
	}
	o.add("docker_containers_running", float64(running))
	o.add("docker_containers_total", float64(len(list)))
	if len(list) > d.max {
		o.add("docker_series_dropped", float64(len(list)-d.max))
		list = list[:d.max]
	}

	d.mu.Lock()
	defer d.mu.Unlock()
	present := map[string]bool{}
	var errs []error
	for _, c := range list {
		present[firstName(c)] = true
		labels := []string{
			"container", trunc(firstName(c)),
			"project", trunc(c.Labels["com.docker.compose.project"]),
			"service", trunc(c.Labels["com.docker.compose.service"]),
		}
		isRunning := 0.0
		if c.State == "running" {
			isRunning = 1
		}
		o.add("docker_container_running", isRunning, labels...)

		var info dockerInspect
		if err := d.get(ctx, "/containers/"+url.PathEscape(c.ID)+"/json", &info); err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", firstName(c), err))
			continue
		}
		o.add("docker_container_restarts_total", float64(info.RestartCount), labels...)
		if info.State.Running {
			if started, err := time.Parse(time.RFC3339Nano, info.State.StartedAt); err == nil {
				o.add("docker_container_uptime_seconds", max(0, now.Sub(started).Seconds()), labels...)
			}
		}
		health := dockerHealthNone
		// Docker to'xtagan konteynerda oxirgi health holatini saqlaydi; faqat ishlayotganlar uchun hisoblanadi.
		if info.State.Running && info.State.Health != nil {
			switch info.State.Health.Status {
			case "healthy":
				health = dockerHealthHealthy
			case "unhealthy":
				health = dockerHealthUnhealthy
			case "starting":
				health = dockerHealthStarting
			}
		}
		o.add("docker_container_health", health, labels...)
		oom := 0.0
		if info.State.OOMKilled {
			oom = 1
		}
		o.add("docker_container_oom_killed", oom, labels...)

		policy := info.HostConfig.RestartPolicy.Name
		if info.State.Running && policy != "" && policy != "no" {
			if started, err := time.Parse(time.RFC3339Nano, info.State.StartedAt); err == nil && now.Sub(started) >= ExpectedAfter {
				d.expected[firstName(c)] = &expectedContainer{labels: labels, lastSeen: now}
			}
		}
		if e, ok := d.expected[firstName(c)]; ok {
			e.lastSeen = now
			o.add("docker_container_expected", 1, labels...)
		} else {
			o.add("docker_container_expected", 0, labels...)
		}
	}
	// Kutilgan konteyner ro'yxatdan yo'qoldi (o'chirildi/qayta yaratilmoqda): running=0 deb xabar beriladi.
	for name, e := range d.expected {
		if present[name] {
			continue
		}
		if now.Sub(e.lastSeen) > ForgetMissingAfter {
			delete(d.expected, name)
			continue
		}
		o.add("docker_container_running", 0, e.labels...)
		o.add("docker_container_expected", 1, e.labels...)
	}
	return o.s, errors.Join(errs...)
}

// firstName konteyner nomi `/` siz (TZ 7.4.4).
func firstName(c dockerListItem) string {
	if len(c.Names) == 0 {
		return c.ID[:min(12, len(c.ID))]
	}
	return strings.TrimPrefix(c.Names[0], "/")
}
