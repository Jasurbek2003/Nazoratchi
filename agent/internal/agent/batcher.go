// Package agent — kollektorlarni jadval bo'yicha ishga tushirish, paketlash, diskdagi navbat va
// core'ga yuborish sikli (TZ 7.2).
package agent

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"reflect"
	"sync"
	"time"

	"nazoratchi/agent/internal/metric"
)

// MaxSeries — bitta host uchun noyob qatorlar chegarasi (TZ 7.3.1).
const MaxSeries = 1000

// FactsEvery — o'zgarmagan faktlar ham shuncha vaqtda bir qo'shiladi (TZ 7.2 Batcher).
const FactsEvery = 10 * time.Minute

// Batcher kelgan namunalarni yig'adi va `Seal` da bitta paketga o'raydi.
type Batcher struct {
	mu          sync.Mutex
	pending     []metric.Sample
	series      map[string]struct{}
	dropped     uint64
	prefix      string
	seq         uint64
	factsFn     func() map[string]any
	lastFacts   map[string]any
	lastFactsAt time.Time
}

// NewBatcher: seq vaqtdan boshlanadi (millisekund), shuning uchun qayta ishga tushganda ham
// monoton oshadi (TZ 7.5.2). batch_id jarayon prefiksi + seq: takrorlanmaydi.
func NewBatcher(now time.Time, facts func() map[string]any) *Batcher {
	var p [4]byte
	_, _ = rand.Read(p[:])
	return &Batcher{
		series:  make(map[string]struct{}),
		prefix:  hex.EncodeToString(p[:]),
		seq:     uint64(now.UnixMilli()),
		factsFn: facts,
	}
}

// Add namunalarni qo'shadi. Yangi qator chegaradan oshsa u tashlanadi (mavjud qatorlar davom etadi).
func (b *Batcher) Add(samples []metric.Sample) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for _, s := range samples {
		if !s.Finite() {
			continue
		}
		key := s.SeriesKey()
		if _, known := b.series[key]; !known {
			if len(b.series) >= MaxSeries {
				b.dropped++
				continue
			}
			b.series[key] = struct{}{}
		}
		b.pending = append(b.pending, s)
	}
}

// AddReserved agentning o'z metrikalarini chegarasiz qo'shadi: `agent_up` yo'qolsa soxta "agent o'chdi"
// alerti chiqardi.
func (b *Batcher) AddReserved(samples []metric.Sample) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for _, s := range samples {
		if s.Finite() {
			b.pending = append(b.pending, s)
		}
	}
}

// SeriesDropped chegaradan oshgani uchun tashlangan yangi qatorlar soni (`agent_series_dropped`).
func (b *Batcher) SeriesDropped() uint64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.dropped
}

// Seal to'plangan namunalardan paket yasaydi; namuna bo'lmasa nil. Faktlar birinchi paketda,
// o'zgarganda va har FactsEvery da qo'shiladi.
func (b *Batcher) Seal(now time.Time) *metric.Batch {
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.pending) == 0 {
		return nil
	}
	b.seq++
	batch := &metric.Batch{
		BatchID: fmt.Sprintf("b-%s-%d", b.prefix, b.seq),
		Seq:     b.seq,
		Samples: b.pending,
	}
	b.pending = nil
	if b.factsFn != nil {
		facts := b.factsFn()
		if b.lastFacts == nil || !reflect.DeepEqual(facts, b.lastFacts) || now.Sub(b.lastFactsAt) >= FactsEvery {
			batch.Facts = facts
			b.lastFacts, b.lastFactsAt = facts, now
		}
	}
	return batch
}

// MarshalFactsForLog faqat sinov/diagnostika uchun.
func MarshalFactsForLog(f map[string]any) string {
	out, _ := json.Marshal(f)
	return string(out)
}
