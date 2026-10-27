package agent

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"nazoratchi/agent/internal/metric"
)

// Self — agentning o'z metrikalari (TZ 7.4.9). Hammasi `agent_*` nomli.
type Self struct {
	mu            sync.Mutex
	version       string
	proc          string
	collectorErrs map[string]uint64
	durations     map[string]float64
	sendFailures  uint64
	clockSkew     float64
	haveSkew      bool
}

func NewSelf(version, proc string) *Self {
	return &Self{version: version, proc: proc, collectorErrs: map[string]uint64{}, durations: map[string]float64{}}
}

func (s *Self) CollectorRun(name string, took time.Duration, err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.durations[name] = took.Seconds()
	if err != nil {
		s.collectorErrs[name]++
	}
}

func (s *Self) SendFailed() {
	s.mu.Lock()
	s.sendFailures++
	s.mu.Unlock()
}

// ClockSkew core vaqti bilan agent vaqti farqi (soniya; musbat = core oldinda).
func (s *Self) ClockSkew(core, local time.Time) {
	s.mu.Lock()
	s.clockSkew, s.haveSkew = core.Sub(local).Seconds(), true
	s.mu.Unlock()
}

// Samples har paketga qo'shiladi: agent_up har paketda 1 (heartbeat).
func (s *Self) Samples(now time.Time, queueFiles int, queueBytes int64, seriesDropped uint64) []metric.Sample {
	ms := now.UnixMilli()
	out := []metric.Sample{
		{N: "agent_up", T: ms, V: 1},
		{N: "agent_version_info", T: ms, V: 1, L: map[string]string{"version": s.version}},
		{N: "agent_queue_files", T: ms, V: float64(queueFiles)},
		{N: "agent_queue_bytes", T: ms, V: float64(queueBytes)},
		{N: "agent_series_dropped", T: ms, V: float64(seriesDropped)},
	}
	s.mu.Lock()
	out = append(out, metric.Sample{N: "agent_send_failures_total", T: ms, V: float64(s.sendFailures)})
	if s.haveSkew {
		out = append(out, metric.Sample{N: "agent_clock_skew_seconds", T: ms, V: s.clockSkew})
	}
	for name, n := range s.collectorErrs {
		out = append(out, metric.Sample{N: "agent_collector_errors", T: ms, V: float64(n), L: map[string]string{"collector": name}})
	}
	for name, d := range s.durations {
		out = append(out, metric.Sample{N: "agent_collect_duration_seconds", T: ms, V: d, L: map[string]string{"collector": name}})
	}
	s.mu.Unlock()
	if rss, ok := readRSS(s.proc); ok {
		out = append(out, metric.Sample{N: "agent_rss_bytes", T: ms, V: rss})
	}
	return out
}

// readRSS `/proc/self/statm` ning 2-maydoni (sahifalarda).
func readRSS(proc string) (float64, bool) {
	data, err := os.ReadFile(filepath.Join(proc, "self", "statm"))
	if err != nil {
		return 0, false
	}
	f := strings.Fields(string(data))
	if len(f) < 2 {
		return 0, false
	}
	pages, err := strconv.ParseFloat(f[1], 64)
	if err != nil {
		return 0, false
	}
	return pages * float64(os.Getpagesize()), true
}
