package collector

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

type netCounters struct{ rx, tx uint64 }

// Net — interfeys tezligi (bayt/s), TZ 7.4.3 F1 qismi. Tezlikni agent o'zi hisoblaydi.
type Net struct {
	proc   string
	ignore []string
	prev   map[string]netCounters
	prevAt time.Time
}

func NewNet(proc string, ignoreIfaces []string) *Net {
	return &Net{proc: proc, ignore: ignoreIfaces}
}

func (n *Net) Name() string { return "net" }

func (n *Net) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	cur, err := n.read()
	if cur == nil {
		return nil, err
	}
	o := newOut(now)
	if elapsed := now.Sub(n.prevAt).Seconds(); !n.prevAt.IsZero() && elapsed > 0 {
		for iface, c := range cur {
			p, ok := n.prev[iface]
			// Hisoblagich kamaysa (interfeys qayta yaratildi) bu o'lchov tashlanadi: manfiy tezlik bo'lmaydi.
			if !ok || c.rx < p.rx || c.tx < p.tx {
				continue
			}
			o.add("net_rx_bytes_per_sec", float64(c.rx-p.rx)/elapsed, "iface", iface)
			o.add("net_tx_bytes_per_sec", float64(c.tx-p.tx)/elapsed, "iface", iface)
		}
	}
	n.prev, n.prevAt = cur, now
	return o.s, err
}

// read yaroqli qatorlarni qaytaradi; buzuq qatorlar xato sifatida qo'shiladi, lekin qolganlari saqlanadi.
func (n *Net) read() (map[string]netCounters, error) {
	data, err := os.ReadFile(filepath.Join(n.proc, "net", "dev"))
	if err != nil {
		return nil, err
	}
	out := map[string]netCounters{}
	var errs []error
	for _, line := range strings.Split(string(data), "\n") {
		name, rest, ok := strings.Cut(line, ":")
		if !ok {
			continue // sarlavha qatorlari
		}
		name = strings.TrimSpace(name)
		if matchAny(n.ignore, name) {
			continue
		}
		f := strings.Fields(rest)
		if len(f) < 9 {
			errs = append(errs, fmt.Errorf("%s: qator qisqa", name))
			continue
		}
		rx, err1 := strconv.ParseUint(f[0], 10, 64)
		tx, err2 := strconv.ParseUint(f[8], 10, 64)
		if err := errors.Join(err1, err2); err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", name, err))
			continue
		}
		out[name] = netCounters{rx: rx, tx: tx}
	}
	return out, errors.Join(errs...)
}
