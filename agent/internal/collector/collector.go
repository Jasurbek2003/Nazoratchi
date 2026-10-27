// Package collector — metrika kollektorlari (TZ 7.4). Har kollektor `/proc` ildizini parametr sifatida
// oladi, shuning uchun testlarda soxta fayl daraxti bilan ishlaydi.
package collector

import (
	"context"
	"math"
	"time"

	"nazoratchi/agent/internal/metric"
)

// Collector bir davrdagi namunalarni qaytaradi. Qisman xatoda ham olingan namunalar qaytariladi.
type Collector interface {
	Name() string
	Collect(ctx context.Context, now time.Time) ([]metric.Sample, error)
}

type out struct {
	ms int64
	s  []metric.Sample
}

func newOut(now time.Time) *out { return &out{ms: now.UnixMilli()} }

// add namuna qo'shadi; kv — belgilar juftliklari (kalit, qiymat). NaN/Inf tashlanadi.
func (o *out) add(name string, v float64, kv ...string) {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return
	}
	var labels map[string]string
	if len(kv) >= 2 {
		labels = make(map[string]string, len(kv)/2)
		for i := 0; i+1 < len(kv); i += 2 {
			labels[kv[i]] = kv[i+1]
		}
	}
	o.s = append(o.s, metric.Sample{N: name, T: o.ms, V: v, L: labels})
}

func percent(v float64) float64 { return math.Max(0, math.Min(100, v)) }
