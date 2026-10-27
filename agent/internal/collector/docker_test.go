package collector

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"nazoratchi/agent/internal/metric"
)

type fakeContainer struct {
	id, name, state, project, service string
	restarts                          int
	startedAgo                        time.Duration
	health                            string
	oom                               bool
	inspectFails                      bool
	policy                            string // bo'sh = "unless-stopped"
}

func dockerHandler(cs []fakeContainer, now time.Time) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/containers/json", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("all") != "1" {
			http.Error(w, "all=1 kerak", 400)
			return
		}
		out := []map[string]any{}
		for _, c := range cs {
			labels := map[string]string{}
			if c.project != "" {
				labels["com.docker.compose.project"] = c.project
				labels["com.docker.compose.service"] = c.service
			}
			out = append(out, map[string]any{"Id": c.id, "Names": []string{"/" + c.name}, "State": c.state, "Labels": labels})
		}
		_ = json.NewEncoder(w).Encode(out)
	})
	mux.HandleFunc("/containers/", func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/containers/"), "/json")
		for _, c := range cs {
			if c.id != id {
				continue
			}
			if c.inspectFails {
				http.Error(w, "xato", 500)
				return
			}
			state := map[string]any{
				"Running": c.state == "running", "Restarting": c.state == "restarting", "OOMKilled": c.oom,
				"StartedAt": now.Add(-c.startedAgo).Format(time.RFC3339Nano),
			}
			if c.health != "" {
				state["Health"] = map[string]any{"Status": c.health}
			}
			policy := c.policy
			if policy == "" {
				policy = "unless-stopped"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"RestartCount": c.restarts, "State": state,
				"HostConfig": map[string]any{"RestartPolicy": map[string]any{"Name": policy}},
			})
			return
		}
		http.NotFound(w, r)
	})
	return mux
}

func TestDockerCollectsContainerMetrics(t *testing.T) {
	now := time.UnixMilli(1761125700000)
	srv := httptest.NewServer(dockerHandler([]fakeContainer{
		{id: "aaa", name: "nazar-web-1", state: "running", project: "nazar", service: "web", restarts: 2, startedAgo: 90 * time.Second, health: "healthy"},
		{id: "bbb", name: "nazar-db-1", state: "exited", project: "nazar", service: "db", restarts: 0},
		{id: "ccc", name: "loose", state: "running", startedAgo: time.Hour, health: "unhealthy", oom: true},
		{id: "ddd", name: "warm", state: "running", startedAgo: time.Second, health: "starting"},
		{id: "eee", name: "gone", state: "exited", health: "unhealthy"},
	}, now))
	defer srv.Close()

	d, err := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 100)
	if err != nil {
		t.Fatal(err)
	}
	got, err := d.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	web := "{container=nazar-web-1,project=nazar,service=web}"
	for key, want := range map[string]float64{
		"docker_containers_running": 3, "docker_containers_total": 5,
		"docker_container_running" + web: 1, "docker_container_restarts_total" + web: 2,
		"docker_container_uptime_seconds" + web: 90, "docker_container_health" + web: 1,
		"docker_container_oom_killed" + web:                                       0,
		"docker_container_running{container=nazar-db-1,project=nazar,service=db}": 0,
		"docker_container_health{container=loose,project=,service=}":              2,
		"docker_container_oom_killed{container=loose,project=,service=}":          1,
		"docker_container_health{container=warm,project=,service=}":               3,
	} {
		if s, ok := m[key]; !ok || s.V != want {
			t.Errorf("%s = %v (bor=%v), %v kutilgan", key, s.V, ok, want)
		}
	}
	// to'xtagan konteynerning eski "unhealthy" holati hisobga olinmaydi
	if s := m["docker_container_health{container=gone,project=,service=}"]; s.V != 0 {
		t.Errorf("exited konteynerda health 0 bo'lishi kerak: %v", s.V)
	}
	// to'xtagan konteynerda uptime yo'q
	if _, ok := m["docker_container_uptime_seconds{container=nazar-db-1,project=nazar,service=db}"]; ok {
		t.Error("exited konteynerda uptime bo'lmasligi kerak")
	}
	for _, s := range got {
		if !nameRe.MatchString(s.N) || !s.Finite() {
			t.Fatalf("yaroqsiz namuna: %+v", s)
		}
	}
}

func TestDockerLimitsContainersAndReportsDropped(t *testing.T) {
	now := time.Now()
	var cs []fakeContainer
	for i := 0; i < 5; i++ {
		cs = append(cs, fakeContainer{id: fmt.Sprintf("id%d", i), name: fmt.Sprintf("c-%d", i), state: "running"})
	}
	srv := httptest.NewServer(dockerHandler(cs, now))
	defer srv.Close()
	d, _ := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 3)
	got, err := d.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if m["docker_series_dropped"].V != 2 || m["docker_containers_total"].V != 5 {
		t.Fatalf("dropped/total: %v %v", m["docker_series_dropped"], m["docker_containers_total"])
	}
	count := 0
	for _, s := range got {
		if s.N == "docker_container_running" {
			count++
		}
	}
	if count != 3 {
		t.Fatalf("faqat 3 konteyner kuzatilishi kerak: %d", count)
	}
}

func TestDockerPartialFailureKeepsOthers(t *testing.T) {
	now := time.Now()
	srv := httptest.NewServer(dockerHandler([]fakeContainer{
		{id: "a", name: "a", state: "running"}, {id: "b", name: "b", state: "running", inspectFails: true},
	}, now))
	defer srv.Close()
	d, _ := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 10)
	got, err := d.Collect(context.Background(), now)
	if err == nil || !strings.Contains(err.Error(), "b:") {
		t.Fatalf("b uchun xato kutilgan: %v", err)
	}
	m := byName(got)
	if _, ok := m["docker_container_restarts_total{container=a,project=,service=}"]; !ok {
		t.Fatal("a konteyner ma'lumoti saqlanishi kerak")
	}
	if _, ok := m["docker_container_running{container=b,project=,service=}"]; !ok {
		t.Fatal("b ning running holati ro'yxatdan olinishi kerak")
	}
}

func TestDockerUnreachableAndBadEndpoint(t *testing.T) {
	d, _ := NewDocker("tcp://127.0.0.1:1", 10)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if _, err := d.Collect(ctx, time.Now()); err == nil {
		t.Fatal("ulanib bo'lmasa xato kerak")
	}
	for _, bad := range []string{"ftp://x", "tcp://", "%%%"} {
		if _, err := NewDocker(bad, 1); err == nil {
			t.Errorf("%q rad etilishi kerak", bad)
		}
	}
}

func TestDockerUnixSocket(t *testing.T) {
	sock := filepath.Join(t.TempDir(), "docker.sock")
	l, err := net.Listen("unix", sock)
	if err != nil {
		t.Skip("unix soket yo'q: ", err)
	}
	srv := &http.Server{Handler: dockerHandler([]fakeContainer{{id: "u", name: "u-1", state: "running"}}, time.Now())}
	go func() { _ = srv.Serve(l) }()
	defer srv.Close()
	d, err := NewDocker("unix://"+sock, 10)
	if err != nil {
		t.Fatal(err)
	}
	got, err := d.Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if byName(got)["docker_containers_total"].V != 1 {
		t.Fatalf("%+v", got)
	}
}

func TestDockerHTTPErrorStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Error(w, "forbidden", http.StatusForbidden) }))
	defer srv.Close()
	d, _ := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 10)
	_, err := d.Collect(context.Background(), time.Now())
	if err == nil || !strings.Contains(err.Error(), "HTTP 403") {
		t.Fatalf("403 xatosi kutilgan: %v", err)
	}
}

func TestDockerExpectedContainerLifecycle(t *testing.T) {
	t0 := time.UnixMilli(1761125700000)
	cs := []fakeContainer{
		{id: "a", name: "old-web", state: "running", startedAgo: 2 * time.Hour},
		{id: "b", name: "young", state: "running", startedAgo: 10 * time.Minute},
		{id: "c", name: "oneshot", state: "running", startedAgo: 3 * time.Hour, policy: "no"},
	}
	current := cs
	now := t0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dockerHandler(current, now).ServeHTTP(w, r)
	}))
	defer srv.Close()
	d, _ := NewDocker(strings.Replace(srv.URL, "http://", "tcp://", 1), 100)
	exp := func(name string) (float64, bool) {
		s, ok := byName(mustCollect(t, d, now))["docker_container_expected{container="+name+",project=,service=}"]
		return s.V, ok
	}

	if v, _ := exp("old-web"); v != 1 {
		t.Fatal("1 soatdan ortiq ishlagan, restart policy bor: kutilgan bo'lishi kerak")
	}
	if v, _ := exp("young"); v != 0 {
		t.Fatal("1 soatdan kam ishlagan: kutilgan emas")
	}
	if v, _ := exp("oneshot"); v != 0 {
		t.Fatal("RestartPolicy=no: kutilgan emas")
	}

	// old-web to'xtadi: hamon kutilgan, running=0
	current = []fakeContainer{{id: "a", name: "old-web", state: "exited"}, cs[1], cs[2]}
	now = t0.Add(time.Minute)
	m := byName(mustCollect(t, d, now))
	if m["docker_container_running{container=old-web,project=,service=}"].V != 0 || m["docker_container_expected{container=old-web,project=,service=}"].V != 1 {
		t.Fatal("to'xtagan kutilgan konteyner: running=0, expected=1")
	}

	// ro'yxatdan butunlay yo'qoldi: 10 daqiqagacha running=0 xabari, keyin unutiladi
	current = []fakeContainer{cs[1], cs[2]}
	now = t0.Add(5 * time.Minute)
	m = byName(mustCollect(t, d, now))
	if s, ok := m["docker_container_running{container=old-web,project=,service=}"]; !ok || s.V != 0 {
		t.Fatal("yo'qolgan kutilgan konteyner uchun running=0 kerak")
	}
	now = t0.Add(20 * time.Minute)
	m = byName(mustCollect(t, d, now))
	if _, ok := m["docker_container_running{container=old-web,project=,service=}"]; ok {
		t.Fatal("10 daqiqadan keyin unutilishi kerak (ataylab olib tashlangan)")
	}
}

func mustCollect(t *testing.T, d *Docker, now time.Time) []metric.Sample {
	t.Helper()
	got, err := d.Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	return got
}
