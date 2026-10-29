package collector

import (
	"context"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

// Faqat butun blok qurilmalar: sda (sda1 emas), vda, xvda, nvme0n1 (nvme0n1p1 emas), mmcblk0.
// `loop*`, `ram*`, `dm-*`, `md*` hisoblanmaydi (TZ 7.4.2).
var wholeDisk = regexp.MustCompile(`^(sd[a-z]+|vd[a-z]+|xvd[a-z]+|hd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)$`)

const sectorBytes = 512 // /proc/diskstats har doim 512 baytlik sektorda

type ioStat struct {
	reads, writes           float64
	readSectors, wrSectors  float64
	readMs, writeMs, ioTick float64
}

// DiskIO — blok qurilmalar o'qish/yozish tezligi, IOPS, band vaqti va kutish (TZ 7.4.2, F2).
type DiskIO struct {
	proc string
	prev map[string]ioStat
	at   time.Time
}

func NewDiskIO(proc string) *DiskIO { return &DiskIO{proc: proc} }

func (d *DiskIO) Name() string { return "diskio" }

func (d *DiskIO) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	data, err := os.ReadFile(filepath.Join(d.proc, "diskstats"))
	if err != nil {
		return nil, err
	}
	cur := map[string]ioStat{}
	for _, line := range strings.Split(string(data), "\n") {
		f := strings.Fields(line)
		if len(f) < 13 || !wholeDisk.MatchString(f[2]) {
			continue
		}
		var v [14]float64
		for i := 3; i < len(f) && i < 14; i++ {
			v[i], _ = strconv.ParseFloat(f[i], 64)
		}
		cur[f[2]] = ioStat{
			reads: v[3], readSectors: v[5], readMs: v[6],
			writes: v[7], wrSectors: v[9], writeMs: v[10],
			ioTick: v[12],
		}
	}
	if len(cur) == 0 && d.prev == nil {
		// Blok qurilma ko'rinmaydi (konteyner/VM): xato emas, shunchaki namuna yo'q.
		return nil, nil
	}
	o := newOut(now)
	dt := now.Sub(d.at).Seconds()
	for dev, c := range cur {
		p, ok := d.prev[dev]
		if !ok || dt <= 0 || c.reads < p.reads || c.writes < p.writes || c.ioTick < p.ioTick {
			continue // birinchi o'lchov yoki hisoblagich qayta boshlangan
		}
		dr, dw := c.reads-p.reads, c.writes-p.writes
		o.add("disk_read_bytes_per_sec", (c.readSectors-p.readSectors)*sectorBytes/dt, "device", dev)
		o.add("disk_write_bytes_per_sec", (c.wrSectors-p.wrSectors)*sectorBytes/dt, "device", dev)
		o.add("disk_read_iops", dr/dt, "device", dev)
		o.add("disk_write_iops", dw/dt, "device", dev)
		o.add("disk_io_util_percent", percent(100*(c.ioTick-p.ioTick)/(dt*1000)), "device", dev)
		await := 0.0
		if dr+dw > 0 {
			await = ((c.readMs - p.readMs) + (c.writeMs - p.writeMs)) / (dr + dw)
		}
		o.add("disk_await_ms", await, "device", dev)
	}
	d.prev, d.at = cur, now
	return o.s, nil
}
