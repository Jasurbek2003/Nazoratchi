package agent

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"nazoratchi/agent/internal/collector"
	"nazoratchi/agent/internal/config"
	"nazoratchi/agent/internal/facts"
	"nazoratchi/agent/internal/metric"
	"nazoratchi/agent/internal/queue"
	"nazoratchi/agent/internal/sender"
	"nazoratchi/agent/internal/update"
)

// BatchEvery — namunalar shuncha vaqt yig'ilib, bitta paketga o'raladi (TZ 7.2 Batcher).
const BatchEvery = 15 * time.Second

// Job — bitta kollektor va uning intervali.
type Job struct {
	C        collector.Collector
	Interval time.Duration
}

type Options struct {
	Cfg     *config.Config
	Token   string
	Version string
	Log     *slog.Logger
	Proc    string        // standart /proc
	Jobs    []Job         // bo'sh bo'lsa sozlamadan quriladi (testlar uchun)
	Batch   time.Duration // standart BatchEvery
	Facts   func() map[string]any
	Update  *update.Updater // nil: yangilanish buyruqlari e'tiborsiz qoldiriladi
}

// BuildJobs yoqilgan va amalga oshirilgan kollektorlarni tuzadi; qolganlari `skipped` da.
func BuildJobs(cfg *config.Config, proc string) (jobs []Job, skipped []string) {
	c := cfg.Collectors
	if c.System.Enabled {
		jobs = append(jobs, Job{collector.NewSystem(proc), c.System.Interval})
	}
	if c.Disk.Enabled {
		jobs = append(jobs, Job{collector.NewDisk(proc, c.Disk.IgnoreFSTypes, nil), c.Disk.Interval})
	}
	if c.DiskIO.Enabled {
		jobs = append(jobs, Job{collector.NewDiskIO(proc), c.DiskIO.Interval})
	}
	if c.Reboot.Enabled {
		jobs = append(jobs, Job{collector.NewReboot(proc, "/var/run/reboot-required", "/boot"), c.Reboot.Interval})
	}
	if c.Certs.Enabled {
		jobs = append(jobs, Job{collector.NewCerts(c.Certs.Globs, c.Certs.StateFile), c.Certs.Interval})
	}
	if c.Net.Enabled {
		jobs = append(jobs, Job{collector.NewNet(proc, c.Net.IgnoreIfaces), c.Net.Interval})
	}
	if c.Docker.Enabled {
		if d, err := collector.NewDocker(c.Docker.Endpoint, c.Docker.MaxContainers); err != nil {
			skipped = append(skipped, "docker ("+err.Error()+")")
		} else {
			jobs = append(jobs, Job{d, c.Docker.Interval})
		}
	}
	if c.Systemd.Enabled {
		if sd, err := collector.NewSystemd(c.Systemd.Units, c.Systemd.HeartbeatsDir, nil); err != nil {
			skipped = append(skipped, "systemd ("+err.Error()+")")
		} else {
			jobs = append(jobs, Job{sd, c.Systemd.Interval})
		}
	}
	if c.Backup.Enabled {
		jobs = append(jobs, Job{collector.NewBackup(c.Backup.Root, c.Backup.AppctlConf), c.Backup.Interval})
	}
	// Quyidagilar keyingi sprintlarda (B5d+) qo'shiladi.
	for name, col := range c.All() {
		switch name {
		case "system", "disk", "diskio", "reboot", "certs", "net", "docker", "systemd", "backup":
		default:
			if col.Enabled {
				skipped = append(skipped, name)
			}
		}
	}
	sort.Strings(skipped)
	return jobs, skipped
}

type runner struct {
	log     *slog.Logger
	q       *queue.Queue
	batcher *Batcher
	self    *Self
	up      *Uploader
	wake    chan struct{}
	now     func() time.Time
}

// Run ctx bekor qilinguncha ishlaydi. To'xtashda oxirgi paketni navbatga yozadi va bir marta yuborib ko'radi.
func Run(ctx context.Context, o Options) error {
	proc := o.Proc
	if proc == "" {
		proc = "/proc"
	}
	every := o.Batch
	if every == 0 {
		every = BatchEvery
	}
	jobs := o.Jobs
	if jobs == nil {
		var skipped []string
		jobs, skipped = BuildJobs(o.Cfg, proc)
		if len(skipped) > 0 {
			o.Log.Info("hali amalga oshirilmagan kollektorlar o'tkazib yuborildi", "collectors", skipped)
		}
	}
	if len(jobs) == 0 {
		return errors.New("yoqilgan kollektor yo'q")
	}
	q, err := queue.Open(o.Cfg.Queue.Dir, o.Cfg.Queue.MaxBytes, o.Cfg.Queue.MaxAge)
	if err != nil {
		return err
	}
	s, err := sender.New(o.Cfg.Core.URL, o.Token, o.Version, o.Cfg.Core.CAFile, o.Cfg.Core.Timeout)
	if err != nil {
		return err
	}
	factsFn := o.Facts
	if factsFn == nil {
		src := facts.Default(o.Cfg.Host.Name)
		src.Proc = proc
		factsFn = src.Collect
	}
	ctx, stop := context.WithCancel(ctx) // yangilanish tayyor bo'lganda agent o'zini toza to'xtatadi
	defer stop()
	self := NewSelf(o.Version, proc)
	r := &runner{
		log: o.Log, q: q, self: self, now: time.Now,
		batcher: NewBatcher(time.Now(), factsFn),
		up:      NewUploader(q, s, self, o.Log),
		wake:    make(chan struct{}, 1),
	}
	if o.Update != nil {
		ur := &updateRunner{
			now: time.Now, updater: o.Update, self: self, stop: stop,
			logf: o.Log.Info, warnf: o.Log.Warn, errorf: o.Log.Error,
		}
		defer ur.wg.Wait()
		r.up.OnCommand = func(c sender.Command) { ur.handle(ctx, c) }
		r.up.OnFirstSend = func() {
			if err := o.Update.Confirm(); err != nil {
				o.Log.Warn("yangilanish tasdig'i yozilmadi", "error", err)
			}
		}
	}
	r.log.Info("agent ishga tushdi", "version", o.Version, "core", o.Cfg.Core.URL, "collectors", len(jobs))

	var wg sync.WaitGroup
	for _, j := range jobs {
		wg.Add(1)
		go func() { defer wg.Done(); r.runJob(ctx, j) }()
	}
	wg.Add(1)
	go func() { defer wg.Done(); r.up.Run(ctx, r.wake) }()
	r.wake <- struct{}{} // oldingi ishdan qolgan navbatni darrov yuborish (qayta ishga tushish, reboot)

	tick := time.NewTicker(every)
	defer tick.Stop()
loop:
	for {
		select {
		case <-ctx.Done():
			break loop
		case <-tick.C:
			r.seal()
		}
	}
	wg.Wait()
	// To'xtash: oxirgi paket saqlanadi va 5 soniya ichida yuborib ko'riladi; bo'lmasa navbatda qoladi.
	r.seal()
	final, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	r.up.Flush(final)
	r.log.Info("agent to'xtadi")
	return nil
}

func (r *runner) seal() {
	now := r.now()
	files, bytes := r.q.Stats()
	r.batcher.AddReserved(r.self.Samples(now, files, bytes, r.batcher.SeriesDropped()))
	b := r.batcher.Seal(now)
	if b == nil {
		return
	}
	data, err := sender.EncodeStored(*b)
	if err != nil {
		r.log.Error("paket kodlanmadi", "error", err)
		return
	}
	dropped, err := r.q.Push(b.Seq, data)
	if err != nil {
		r.log.Error("paket navbatga yozilmadi", "error", err)
		return
	}
	if dropped > 0 {
		r.log.Warn("navbat to'ldi: eng eski paketlar o'chirildi", "dropped", dropped)
	}
	select {
	case r.wake <- struct{}{}:
	default:
	}
}

func jitter(d time.Duration) time.Duration {
	return time.Duration(float64(d) * (0.9 + 0.2*rand.Float64()))
}

// runJob: birinchi yig'ish darhol, keyin interval ±10% jitter bilan (TZ 7.2 Scheduler).
func (r *runner) runJob(ctx context.Context, j Job) {
	var busy atomic.Bool
	for {
		r.collectOnce(ctx, j, &busy)
		select {
		case <-ctx.Done():
			return
		case <-time.After(jitter(j.Interval)):
		}
	}
}

var errBusy = errors.New("oldingi yig'ish tugamagan")

// collectOnce kollektorni `interval/2` timeout bilan ishga tushiradi. Osilib qolgan kollektor (masalan,
// o'lik NFS dagi statfs) agentni to'xtatmaydi; u tugamaguncha keyingi davrlar o'tkazib yuboriladi.
func (r *runner) collectOnce(ctx context.Context, j Job, busy *atomic.Bool) {
	name := j.C.Name()
	if !busy.CompareAndSwap(false, true) {
		r.log.Warn("kollektor hali tugamagan, davr o'tkazib yuborildi", "collector", name)
		r.self.CollectorRun(name, 0, errBusy)
		return
	}
	type result struct {
		s   []metric.Sample
		err error
	}
	ch := make(chan result, 1)
	cctx, cancel := context.WithTimeout(ctx, j.Interval/2)
	defer cancel()
	start := r.now()
	go func() {
		s, err := j.C.Collect(cctx, start)
		busy.Store(false)
		ch <- result{s, err}
	}()
	select {
	case res := <-ch:
		took := r.now().Sub(start)
		if res.err != nil {
			r.log.Warn("kollektor xatosi", "collector", name, "error", res.err)
		}
		r.self.CollectorRun(name, took, res.err)
		r.batcher.Add(res.s)
	case <-cctx.Done():
		if ctx.Err() != nil {
			return // to'xtash
		}
		r.log.Warn("kollektor timeout", "collector", name, "timeout", (j.Interval / 2).String())
		r.self.CollectorRun(name, j.Interval/2, fmt.Errorf("timeout"))
	}
}
