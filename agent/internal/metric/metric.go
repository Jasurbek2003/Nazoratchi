// Package metric — agent va core o'rtasidagi paket va namuna turlari (TZ 7.5.2).
package metric

import (
	"math"
	"sort"
	"strings"
)

// Sample — bitta o'lchov. Maydon nomlari protokolga mos (n, t, v, l).
type Sample struct {
	N string            `json:"n"`
	T int64             `json:"t"` // UTC, millisekund
	V float64           `json:"v"`
	L map[string]string `json:"l,omitempty"`
}

// Finite — NaN/Inf JSON ga yozilmaydi va core ularni rad etadi.
func (s Sample) Finite() bool { return !math.IsNaN(s.V) && !math.IsInf(s.V, 0) }

// SeriesKey — noyob qator kaliti: nom + saralangan belgilar.
func (s Sample) SeriesKey() string {
	if len(s.L) == 0 {
		return s.N
	}
	keys := make([]string, 0, len(s.L))
	for k := range s.L {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	b.WriteString(s.N)
	b.WriteByte('{')
	for i, k := range keys {
		if i > 0 {
			b.WriteByte(',')
		}
		b.WriteString(k)
		b.WriteByte('=')
		b.WriteString(s.L[k])
	}
	b.WriteByte('}')
	return b.String()
}

// Batch — core'ga yuboriladigan paket. `sent_at` navbatda saqlanmaydi: har yuborishda yangilanadi,
// core agent soati siljishini shundan aniqlaydi (TZ 7.5.2). `batch_id` esa qayta urinishda o'zgarmaydi.
type Batch struct {
	BatchID string         `json:"batch_id"`
	Seq     uint64         `json:"seq"`
	SentAt  string         `json:"sent_at,omitempty"`
	Samples []Sample       `json:"samples"`
	Facts   map[string]any `json:"facts,omitempty"`
}
