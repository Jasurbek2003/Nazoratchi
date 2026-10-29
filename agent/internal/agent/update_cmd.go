package agent

import (
	"context"
	"errors"
	"sync"
	"time"

	"nazoratchi/agent/internal/sender"
	"nazoratchi/agent/internal/update"
)

// updateRetry — muvaffaqiyatsiz yoki rad etilgan yangilanish buyrug'i qayta ishlanmaguncha kutish.
// Core buyruqni har paketda (15 s) takrorlaydi; 64 MB ni shuncha tez-tez yuklamaslik uchun.
const updateRetry = 5 * time.Minute

type updateRunner struct {
	mu      sync.Mutex
	last    time.Time
	now     func() time.Time
	updater *update.Updater
	self    *Self
	stop    context.CancelFunc
	logf    func(msg string, args ...any)
	warnf   func(msg string, args ...any)
	errorf  func(msg string, args ...any)
	wg      sync.WaitGroup
}

// handle core buyrug'ini qayta ishlaydi. `update` fonda bajariladi: yuklash yuborishni to'xtatmaydi.
// Muvaffaqiyatda `stop` chaqiriladi: agent toza chiqadi va systemd qayta ishga tushiradi.
func (u *updateRunner) handle(ctx context.Context, c sender.Command) {
	if c.Type != "update" {
		u.logf("core buyrug'i e'tiborsiz qoldirildi", "type", c.Type)
		return
	}
	u.mu.Lock()
	if !u.last.IsZero() && u.now().Sub(u.last) < updateRetry {
		u.mu.Unlock()
		return
	}
	u.last = u.now()
	u.mu.Unlock()

	u.wg.Add(1)
	go func() {
		defer u.wg.Done()
		v, err := u.updater.Stage(ctx, update.Command{Version: c.Version, SHA256: c.SHA256})
		var rej *update.RejectError
		switch {
		case err == nil:
			u.logf("yangilanish tayyor: agent qayta ishga tushadi", "version", v.String())
			u.stop()
		case errors.As(err, &rej):
			u.self.UpdateRejected()
			u.errorf("yangilanish rad etildi (agent_update_rejected)", "version", c.Version, "reason", rej.Reason)
		case errors.Is(err, update.ErrBusy), errors.Is(err, context.Canceled):
		default:
			u.warnf("yangilanish yuklanmadi, keyinroq qayta uriniladi", "version", c.Version, "error", err)
		}
	}()
}
