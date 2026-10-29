package agent

import (
	"context"
	"log/slog"
	"math/rand/v2"
	"time"

	"nazoratchi/agent/internal/queue"
	"nazoratchi/agent/internal/sender"
)

// backoffSteps — TZ 7.2 Sender: 1, 2, 4, 8, 16, 30 s (±10% jitter).
var backoffSteps = []time.Duration{1, 2, 4, 8, 16, 30}

const (
	unauthorizedWait = 5 * time.Minute // TZ 7.5.2: 401 -> 5 daqiqa kutish
	revokedAfter     = 10              // ketma-ket 401 -> "token bekor qilingan"
)

// Uploader navbatdagi paketlarni eskisidan boshlab yuboradi.
type Uploader struct {
	q      *queue.Queue
	s      *sender.Sender
	log    *slog.Logger
	self   *Self
	now    func() time.Time
	rnd    func() float64
	fails  int  // ketma-ket muvaffaqiyatsizliklar (backoff uchun)
	sentOK bool // birinchi muvaffaqiyatli paket Info darajasida qayd etilgan (install.sh kutadi)
	unauth int
	next   time.Time // shu vaqtgacha urinilmaydi

	// OnCommand core javobidagi har buyruq uchun chaqiriladi (nil bo'lsa e'tiborsiz qoldiriladi).
	OnCommand func(sender.Command)
	// OnFirstSend jarayondagi birinchi muvaffaqiyatli paketdan keyin chaqiriladi (yangilanishni tasdiqlash).
	OnFirstSend func()

	skewWarnedAt time.Time // soat farqi haqidagi oxirgi ogohlantirish
	skewed       bool      // hozir farq chegaradan katta
}

func NewUploader(q *queue.Queue, s *sender.Sender, self *Self, log *slog.Logger) *Uploader {
	return &Uploader{q: q, s: s, self: self, log: log, now: time.Now, rnd: rand.Float64}
}

func (u *Uploader) backoff() time.Duration {
	step := backoffSteps[min(u.fails-1, len(backoffSteps)-1)] * time.Second
	return time.Duration(float64(step) * (0.9 + 0.2*u.rnd()))
}

// Flush navbatni bo'shatadi. Qaytadi: keyingi urinishgacha kutish (0 — navbat bo'sh).
func (u *Uploader) Flush(ctx context.Context) time.Duration {
	if wait := u.next.Sub(u.now()); wait > 0 {
		return wait
	}
	for ctx.Err() == nil {
		name, data, ok, err := u.q.Oldest()
		if err != nil {
			u.log.Error("navbat o'qilmadi", "error", err)
			u.fails++
			return u.setNext(u.backoff())
		}
		if !ok {
			u.fails, u.unauth = 0, 0
			return 0
		}
		batch, err := sender.DecodeStored(data)
		if err != nil {
			u.log.Error("buzuq paket o'chirildi", "file", name, "error", err)
			_ = u.q.Remove(name)
			continue
		}
		res := u.s.Send(ctx, batch)
		switch res.Outcome {
		case sender.OK:
			_ = u.q.Remove(name)
			u.fails, u.unauth = 0, 0
			if t, err := time.Parse(time.RFC3339Nano, res.Resp.ServerTime); err == nil {
				u.self.ClockSkew(t, res.ReceivedAt)
				u.checkSkew(t.Sub(res.ReceivedAt))
			}
			if !u.sentOK {
				u.sentOK = true
				u.log.Info("paket yuborildi (birinchi)", "batch_id", batch.BatchID)
				if u.OnFirstSend != nil {
					u.OnFirstSend()
				}
			}
			u.log.Debug("paket yuborildi", "batch_id", batch.BatchID, "accepted", res.Resp.Accepted, "rejected", res.Resp.Rejected)
			if res.Resp.ClockSkew {
				u.log.Warn("core agent soatida siljish aniqladi", "batch_id", batch.BatchID)
			}
			for _, c := range res.Resp.Commands {
				if u.OnCommand != nil {
					u.OnCommand(c)
					continue
				}
				u.log.Info("core buyrug'i e'tiborsiz qoldirildi", "type", c.Type)
			}
		case sender.Drop:
			_ = u.q.Remove(name)
			u.self.SendFailed()
			u.log.Warn("paket rad etildi", "batch_id", batch.BatchID, "reason", res.Detail)
		default:
			u.self.SendFailed()
			u.fails++
			wait := u.backoff()
			if res.Status == 401 {
				u.unauth++
				wait = unauthorizedWait
				if u.unauth == revokedAfter {
					u.log.Error("token bekor qilingan bo'lishi mumkin; yig'ish davom etadi", "attempts", u.unauth)
				}
			} else {
				u.unauth = 0
				if res.RetryAfter > 0 {
					wait = res.RetryAfter
				}
			}
			u.log.Warn("yuborilmadi", "batch_id", batch.BatchID, "reason", res.Detail, "retry_in", wait.Round(time.Millisecond).String())
			return u.setNext(wait)
		}
	}
	return 0
}

func (u *Uploader) setNext(wait time.Duration) time.Duration {
	u.next = u.now().Add(wait)
	return wait
}

// Run `wake` signalida yoki qayta urinish vaqti kelganda Flush ni chaqiradi.
func (u *Uploader) Run(ctx context.Context, wake <-chan struct{}) {
	var timer <-chan time.Time
	for {
		select {
		case <-ctx.Done():
			return
		case <-wake:
		case <-timer:
		}
		if wait := u.Flush(ctx); wait > 0 {
			timer = time.After(wait)
		} else {
			timer = nil
		}
	}
}

const (
	// MaxClockSkew — shundan katta farq ma'lumot sifatiga ta'sir qiladi (TZ FR-AGT-012, FR-HST-013).
	MaxClockSkew  = 5 * time.Second
	skewWarnEvery = 10 * time.Minute
)

// checkSkew core vaqti bilan farq chegaradan oshsa ogohlantiradi (spam qilmasdan) va tuzalganda xabar beradi.
// Farq `agent_clock_skew_seconds` metrikasi sifatida ham yuboriladi (panelda belgi chiqadi).
func (u *Uploader) checkSkew(diff time.Duration) {
	abs := diff
	if abs < 0 {
		abs = -abs
	}
	now := u.now()
	switch {
	case abs > MaxClockSkew && (!u.skewed || now.Sub(u.skewWarnedAt) >= skewWarnEvery):
		u.skewed, u.skewWarnedAt = true, now
		u.log.Warn("agent soati core soatidan farq qiladi", "skew_seconds", diff.Seconds(), "limit_seconds", MaxClockSkew.Seconds())
	case abs <= MaxClockSkew && u.skewed:
		u.skewed = false
		u.log.Info("agent soati core soatiga mos keldi", "skew_seconds", diff.Seconds())
	}
}
