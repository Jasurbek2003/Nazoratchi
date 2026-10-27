package agent

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"nazoratchi/agent/internal/config"
	"nazoratchi/agent/internal/metric"
	"nazoratchi/agent/internal/queue"
	"nazoratchi/agent/internal/sender"
)

var quiet = slog.New(slog.NewTextHandler(io.Discard, nil))

func sample(name string, v float64, kv ...string) metric.Sample {
	l := map[string]string{}
	for i := 0; i+1 < len(kv); i += 2 {
		l[kv[i]] = kv[i+1]
	}
	return metric.Sample{N: name, T: 1, V: v, L: l}
}

// ---------- Batcher ----------

func TestBatcherSealEmptyIsNil(t *testing.T) {
	b := NewBatcher(time.Now(), nil)
	if b.Seal(time.Now()) != nil {
		t.Fatal("namuna bo'lmasa paket yasalmasligi kerak")
	}
}

func TestBatcherSeqMonotonicAndIDsUnique(t *testing.T) {
	b := NewBatcher(time.UnixMilli(1000), nil)
	var last uint64
	ids := map[string]bool{}
	for i := 0; i < 5; i++ {
		b.Add([]metric.Sample{sample("load1", 1)})
		batch := b.Seal(time.Now())
		if batch.Seq <= last || ids[batch.BatchID] {
			t.Fatalf("seq/batch_id takrorlandi: %+v", batch)
		}
		last, ids[batch.BatchID] = batch.Seq, true
		if len(batch.BatchID) > 64 {
			t.Fatal("batch_id 64 belgidan oshmasligi kerak")
		}
	}
}

func TestBatcherFactsFirstChangedAndPeriodic(t *testing.T) {
	facts := map[string]any{"kernel_running": "6.8.0-139"}
	b := NewBatcher(time.Now(), func() map[string]any { return facts })
	now := time.Now()
	seal := func(at time.Time) *metric.Batch {
		b.Add([]metric.Sample{sample("load1", 1)})
		return b.Seal(at)
	}
	if seal(now).Facts == nil {
		t.Fatal("birinchi paketda faktlar bo'lishi kerak")
	}
	if seal(now.Add(15*time.Second)).Facts != nil {
		t.Fatal("o'zgarmagan faktlar har paketda yuborilmasligi kerak")
	}
	facts = map[string]any{"kernel_running": "6.8.0-147"}
	if f := seal(now.Add(30 * time.Second)).Facts; f["kernel_running"] != "6.8.0-147" {
		t.Fatalf("o'zgargan faktlar yuborilishi kerak: %v", f)
	}
	if seal(now.Add(45*time.Second)).Facts != nil {
		t.Fatal("yana o'zgarmadi")
	}
	if seal(now.Add(30*time.Second+FactsEvery)).Facts == nil {
		t.Fatal("10 daqiqada bir marta o'zgarmasa ham yuborilishi kerak")
	}
}

func TestBatcherSeriesLimitDropsNewButKeepsExisting(t *testing.T) {
	b := NewBatcher(time.Now(), nil)
	var many []metric.Sample
	for i := 0; i < MaxSeries+50; i++ {
		many = append(many, sample("fs_used_percent", 1, "mount", fmt.Sprintf("/m%d", i)))
	}
	b.Add(many)
	if got := b.SeriesDropped(); got != 50 {
		t.Fatalf("tashlangan = %d, 50 kutilgan", got)
	}
	b.Seal(time.Now())
	b.Add([]metric.Sample{sample("fs_used_percent", 2, "mount", "/m0"), sample("fs_used_percent", 2, "mount", "/yangi")})
	batch := b.Seal(time.Now())
	if len(batch.Samples) != 1 || batch.Samples[0].L["mount"] != "/m0" {
		t.Fatalf("mavjud qator davom etishi, yangisi tashlanishi kerak: %+v", batch.Samples)
	}
}

func TestBatcherDropsNonFiniteAndReservedBypassesLimit(t *testing.T) {
	b := NewBatcher(time.Now(), nil)
	b.Add([]metric.Sample{sample("a", math.NaN()), sample("b", math.Inf(1))})
	b.AddReserved([]metric.Sample{sample("agent_up", 1), sample("c", math.NaN())})
	batch := b.Seal(time.Now())
	if len(batch.Samples) != 1 || batch.Samples[0].N != "agent_up" {
		t.Fatalf("%+v", batch.Samples)
	}
	// JSON ga yozilishi kerak (NaN bo'lsa xato berardi)
	if _, err := json.Marshal(batch); err != nil {
		t.Fatal(err)
	}
}

// ---------- Uploader ----------

type fakeCore struct {
	mu       sync.Mutex
	statuses []int // navbat bilan; tugasa 200
	header   string
	got      []metric.Batch
	srv      *httptest.Server
}

func newCore(t *testing.T, statuses ...int) *fakeCore {
	t.Helper()
	c := &fakeCore{statuses: statuses}
	c.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		zr, err := gzip.NewReader(r.Body)
		if err != nil {
			w.WriteHeader(400)
			return
		}
		raw, _ := io.ReadAll(zr)
		var b metric.Batch
		_ = json.Unmarshal(raw, &b)
		c.mu.Lock()
		defer c.mu.Unlock()
		status := 200
		if len(c.statuses) > 0 {
			status, c.statuses = c.statuses[0], c.statuses[1:]
		}
		if c.header != "" {
			w.Header().Set("Retry-After", c.header)
		}
		if status != 200 {
			w.WriteHeader(status)
			return
		}
		c.got = append(c.got, b)
		_, _ = w.Write([]byte(`{"ok":true,"accepted":1,"rejected":0,"server_time":"2026-10-27T10:00:00.000Z"}`))
	}))
	t.Cleanup(c.srv.Close)
	return c
}

func (c *fakeCore) batches() []metric.Batch {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]metric.Batch(nil), c.got...)
}

func newUploader(t *testing.T, core *fakeCore) (*Uploader, *queue.Queue, *time.Time) {
	t.Helper()
	q, err := queue.Open(filepath.Join(t.TempDir(), "q"), 1<<20, time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	s, err := sender.New(core.srv.URL, "agt_x", "t", "", 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	u := NewUploader(q, s, NewSelf("t", "/yoq"), quiet)
	clock := time.Now()
	u.now = func() time.Time { return clock }
	u.rnd = func() float64 { return 0.5 } // jitter = 1.0
	return u, q, &clock
}

func push(t *testing.T, q *queue.Queue, seq uint64) {
	t.Helper()
	data, err := sender.EncodeStored(metric.Batch{BatchID: fmt.Sprintf("b-%d", seq), Seq: seq, Samples: []metric.Sample{sample("load1", 1)}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := q.Push(seq, data); err != nil {
		t.Fatal(err)
	}
}

func TestUploaderDrainsInOrder(t *testing.T) {
	core := newCore(t)
	u, q, _ := newUploader(t, core)
	for _, seq := range []uint64{3, 1, 2} {
		push(t, q, seq)
	}
	if wait := u.Flush(context.Background()); wait != 0 {
		t.Fatalf("navbat bo'shashi kerak: %v", wait)
	}
	got := core.batches()
	if len(got) != 3 || got[0].Seq != 1 || got[1].Seq != 2 || got[2].Seq != 3 {
		t.Fatalf("tartib noto'g'ri: %+v", got)
	}
	if files, _ := q.Stats(); files != 0 {
		t.Fatal("yuborilganlar navbatdan o'chishi kerak")
	}
}

func TestUploaderBackoffGrowsCapsAndResets(t *testing.T) {
	core := newCore(t, 500, 500, 500, 500, 500, 500, 500) // 7 xato, keyin 200
	u, q, clock := newUploader(t, core)
	push(t, q, 1)
	want := []time.Duration{1, 2, 4, 8, 16, 30, 30}
	for i, w := range want {
		wait := u.Flush(context.Background())
		if wait != w*time.Second {
			t.Fatalf("%d-urinish: kutish %v, %v kutilgan", i+1, wait, w*time.Second)
		}
		// kutish tugamasdan qayta urinilmaydi (server so'rovi sarflanmaydi)
		if again := u.Flush(context.Background()); again <= 0 || again > wait {
			t.Fatalf("kutish davrida urinmaslik kerak: %v", again)
		}
		*clock = clock.Add(wait)
	}
	if wait := u.Flush(context.Background()); wait != 0 {
		t.Fatalf("muvaffaqiyatdan keyin 0: %v", wait)
	}
	push(t, q, 2)
	core.mu.Lock()
	core.statuses = []int{503}
	core.mu.Unlock()
	if wait := u.Flush(context.Background()); wait != time.Second {
		t.Fatalf("muvaffaqiyatdan keyin backoff 1 s dan boshlanishi kerak: %v", wait)
	}
}

func TestUploaderRetryAfterAnd401(t *testing.T) {
	core := newCore(t, 429, 401)
	core.header = "7"
	u, q, clock := newUploader(t, core)
	push(t, q, 1)
	if wait := u.Flush(context.Background()); wait != 7*time.Second {
		t.Fatalf("Retry-After hurmat qilinishi kerak: %v", wait)
	}
	*clock = clock.Add(7 * time.Second)
	core.header = ""
	if wait := u.Flush(context.Background()); wait != unauthorizedWait {
		t.Fatalf("401 da 5 daqiqa kutish kerak: %v", wait)
	}
	if files, _ := q.Stats(); files != 1 {
		t.Fatal("paket navbatda qolishi kerak (yig'ish davom etadi)")
	}
}

func TestUploaderDropsRejectedAndCorruptThenContinues(t *testing.T) {
	core := newCore(t, 400) // 1-paket rad etiladi
	u, q, _ := newUploader(t, core)
	push(t, q, 1)
	if _, err := q.Push(2, []byte("buzuq")); err != nil { // 2-fayl buzuq
		t.Fatal(err)
	}
	push(t, q, 3)
	if wait := u.Flush(context.Background()); wait != 0 {
		t.Fatalf("hammasi tozalanishi kerak: %v", wait)
	}
	got := core.batches()
	if len(got) != 1 || got[0].Seq != 3 {
		t.Fatalf("faqat 3-paket yetib borishi kerak: %+v", got)
	}
	if files, _ := q.Stats(); files != 0 {
		t.Fatal("rad etilgan va buzuq fayllar o'chirilishi kerak")
	}
}

func TestUploaderRecordsClockSkew(t *testing.T) {
	core := newCore(t)
	u, q, _ := newUploader(t, core)
	push(t, q, 1)
	u.Flush(context.Background())
	found := false
	for _, s := range u.self.Samples(time.Now(), 0, 0, 0) {
		found = found || s.N == "agent_clock_skew_seconds"
	}
	if !found {
		t.Fatal("agent_clock_skew_seconds yo'q")
	}
}

// ---------- Self ----------

func TestSelfMetricsAlwaysIncludeUpAndVersion(t *testing.T) {
	s := NewSelf("1.2.3", "/yoq")
	s.CollectorRun("disk", 120*time.Millisecond, fmt.Errorf("x"))
	s.SendFailed()
	by := map[string]metric.Sample{}
	for _, m := range s.Samples(time.Now(), 4, 1024, 2) {
		by[m.SeriesKey()] = m
	}
	for key, want := range map[string]float64{
		"agent_up": 1, "agent_version_info{version=1.2.3}": 1, "agent_queue_files": 4, "agent_queue_bytes": 1024,
		"agent_series_dropped": 2, "agent_send_failures_total": 1, "agent_collector_errors{collector=disk}": 1,
	} {
		if by[key].V != want {
			t.Errorf("%s = %v, %v kutilgan", key, by[key].V, want)
		}
	}
	if _, ok := by["agent_clock_skew_seconds"]; ok {
		t.Error("core javobi kelmaguncha siljish chiqmasligi kerak")
	}
}

// ---------- Run (yuqoridan pastgacha) ----------

type fixed struct{ name string }

func (f fixed) Name() string { return f.name }
func (f fixed) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	return []metric.Sample{{N: "load1", T: now.UnixMilli(), V: 0.5}}, nil
}

type hang struct{ release chan struct{} }

func (h hang) Name() string { return "hang" }
func (h hang) Collect(ctx context.Context, _ time.Time) ([]metric.Sample, error) {
	<-h.release
	return nil, nil
}

func testCfg(t *testing.T, url string) *config.Config {
	t.Helper()
	cfg := config.Default()
	cfg.Core.URL = url
	cfg.Queue.Dir = filepath.Join(t.TempDir(), "queue")
	return cfg
}

func waitFor(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("kutilgan holat bo'lmadi: %s", what)
}

func TestRunDeliversBatchesWithSelfMetricsAndStopsCleanly(t *testing.T) {
	core := newCore(t)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		done <- Run(ctx, Options{
			Cfg: testCfg(t, core.srv.URL), Token: "agt_x", Version: "t", Log: quiet, Proc: "/yoq",
			Jobs:  []Job{{C: fixed{"fixed"}, Interval: 20 * time.Millisecond}},
			Batch: 50 * time.Millisecond, Facts: func() map[string]any { return map[string]any{"hostname": "h"} },
		})
	}()
	waitFor(t, "kamida 2 paket", func() bool { return len(core.batches()) >= 2 })
	cancel()
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	got := core.batches()
	names := map[string]bool{}
	for _, s := range got[0].Samples {
		names[s.N] = true
	}
	if !names["load1"] || !names["agent_up"] || !names["agent_version_info"] {
		t.Fatalf("birinchi paket: %v", names)
	}
	if got[0].Facts["hostname"] != "h" || got[1].Facts != nil {
		t.Fatalf("faktlar faqat birinchi paketda: %+v / %+v", got[0].Facts, got[1].Facts)
	}
	for i := 1; i < len(got); i++ {
		if got[i].Seq <= got[i-1].Seq {
			t.Fatal("seq oshib borishi kerak")
		}
	}
}

func TestRunBuffersWhileCoreIsDownThenDeliversInOrder(t *testing.T) {
	core := newCore(t, 503, 503, 503, 503, 503, 503) // dastlab o'chiq
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	cfg := testCfg(t, core.srv.URL)
	go func() {
		done <- Run(ctx, Options{
			Cfg: cfg, Token: "agt_x", Version: "t", Log: quiet, Proc: "/yoq",
			Jobs:  []Job{{C: fixed{"fixed"}, Interval: 20 * time.Millisecond}},
			Batch: 40 * time.Millisecond, Facts: func() map[string]any { return nil },
		})
	}()
	time.Sleep(300 * time.Millisecond)
	cancel()
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	q, _ := queue.Open(cfg.Queue.Dir, cfg.Queue.MaxBytes, cfg.Queue.MaxAge)
	if files, _ := q.Stats(); files == 0 {
		t.Fatal("core o'chiqligida paketlar diskdagi navbatda qolishi kerak")
	}
	// Qayta ishga tushish: core tirilgan, navbat vaqt tartibida bo'shaydi.
	core.mu.Lock()
	core.statuses = nil
	core.mu.Unlock()
	ctx2, cancel2 := context.WithCancel(context.Background())
	done2 := make(chan error, 1)
	go func() {
		done2 <- Run(ctx2, Options{
			Cfg: cfg, Token: "agt_x", Version: "t", Log: quiet, Proc: "/yoq",
			Jobs:  []Job{{C: fixed{"fixed"}, Interval: time.Hour}},
			Batch: time.Hour, Facts: func() map[string]any { return nil },
		})
	}()
	waitFor(t, "navbat bo'shashi", func() bool { files, _ := q.Stats(); return files == 0 && len(core.batches()) > 0 })
	cancel2()
	<-done2
	got := core.batches()
	for i := 1; i < len(got); i++ {
		if got[i].Seq <= got[i-1].Seq {
			t.Fatalf("tartib buzildi: %d -> %d", got[i-1].Seq, got[i].Seq)
		}
	}
}

func TestRunHangingCollectorDoesNotBlockOthers(t *testing.T) {
	core := newCore(t)
	h := hang{release: make(chan struct{})}
	defer close(h.release)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		done <- Run(ctx, Options{
			Cfg: testCfg(t, core.srv.URL), Token: "agt_x", Version: "t", Log: quiet, Proc: "/yoq",
			Jobs: []Job{
				{C: h, Interval: 40 * time.Millisecond},
				{C: fixed{"fixed"}, Interval: 20 * time.Millisecond},
			},
			Batch: 50 * time.Millisecond, Facts: func() map[string]any { return nil },
		})
	}()
	waitFor(t, "paket yetib borishi", func() bool { return len(core.batches()) >= 2 })
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("osilgan kollektor agentni to'xtatishni bloklamasligi kerak")
	}
	foundErr := false
	for _, b := range core.batches() {
		for _, s := range b.Samples {
			if s.N == "agent_collector_errors" && s.L["collector"] == "hang" && s.V > 0 {
				foundErr = true
			}
		}
	}
	if !foundErr {
		t.Fatal("osilgan kollektor agent_collector_errors ni oshirishi kerak")
	}
}

func TestRunRejectsNoCollectors(t *testing.T) {
	cfg := testCfg(t, "http://127.0.0.1:1")
	cfg.Collectors.System.Enabled, cfg.Collectors.Disk.Enabled, cfg.Collectors.Net.Enabled = false, false, false
	cfg.Collectors.DiskIO.Enabled, cfg.Collectors.Docker.Enabled, cfg.Collectors.Systemd.Enabled = false, false, false
	cfg.Collectors.Backup.Enabled, cfg.Collectors.Certs.Enabled = false, false
	cfg.Collectors.SSH.Enabled, cfg.Collectors.Apt.Enabled = false, false
	if err := Run(context.Background(), Options{Cfg: cfg, Log: quiet}); err == nil {
		t.Fatal("kollektorsiz ishga tushmasligi kerak")
	}
}

func TestBuildJobsSkipsUnimplemented(t *testing.T) {
	jobs, skipped := BuildJobs(config.Default(), "/proc")
	if len(jobs) != 6 {
		t.Fatalf("system, disk, net, docker, systemd, backup kutilgan: %d", len(jobs))
	}
	names := map[string]bool{}
	for _, j := range jobs {
		names[j.C.Name()] = true
	}
	for _, n := range []string{"system", "disk", "net", "docker", "systemd", "backup"} {
		if !names[n] {
			t.Fatalf("%s yo'q: %v", n, names)
		}
	}
	if strings.Join(skipped, ",") != "apt,certs,diskio,ssh" { // saralangan
		t.Fatalf("o'tkazib yuborilganlar: %v", skipped)
	}

	bad := config.Default()
	bad.Collectors.Docker.Endpoint = "ftp://x"
	jobs, skipped = BuildJobs(bad, "/proc")
	if len(jobs) != 5 || !strings.Contains(strings.Join(skipped, ","), "docker (") {
		t.Fatalf("noto'g'ri docker endpoint o'tkazib yuborilishi kerak: %d %v", len(jobs), skipped)
	}

	off := config.Default()
	off.Collectors.Systemd.Enabled, off.Collectors.Backup.Enabled = false, false
	if jobs, _ = BuildJobs(off, "/proc"); len(jobs) != 4 {
		t.Fatalf("o'chirilgan kollektorlar job bo'lmasligi kerak: %d", len(jobs))
	}

	badUnit := config.Default() // Validate'dan o'tmagan bo'lsa ham systemd ishga tushmaydi
	badUnit.Collectors.Systemd.Units = []string{"--all"}
	jobs, skipped = BuildJobs(badUnit, "/proc")
	if len(jobs) != 5 || !strings.Contains(strings.Join(skipped, ","), "systemd (") {
		t.Fatalf("yaroqsiz unit: %d %v", len(jobs), skipped)
	}
}
