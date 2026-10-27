"""Monitor holat mashinasi: ping yo'q -> bir marta alert -> eslatmalar -> tiklanish."""

from __future__ import annotations

import html
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from nazoratchi_watchdog.state import State, StateStore

log = logging.getLogger("nazoratchi_watchdog.monitor")

TASHKENT = timezone(timedelta(hours=5), "Asia/Tashkent")  # DST yo'q, tzdata kerak emas
DEGRADED_PINGS = 2
MAX_STARTUP_GRACE_S = 90.0


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def wall(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()


class Notifier(Protocol):
    def send(self, text: str) -> bool: ...


def fmt_duration(seconds: float) -> str:
    if seconds < 90:
        return f"{round(seconds)} soniya"
    minutes = round(seconds / 60)
    if minutes < 120:
        return f"{minutes} daqiqa"
    hours, rest = divmod(minutes, 60)
    return f"{hours} soat {rest} daqiqa" if rest else f"{hours} soat"


def fmt_time(wall: float) -> str:
    return datetime.fromtimestamp(wall, TASHKENT).strftime("%H:%M")


@dataclass
class _Action:
    text: str
    commit: Callable[[], None]


class Monitor:
    def __init__(
        self,
        *,
        timeout_s: float,
        remind_s: float,
        store: StateStore,
        notifier: Notifier,
        clock: Clock | None = None,
        startup_grace_s: float | None = None,
    ) -> None:
        self._timeout = timeout_s
        self._remind = remind_s
        self._store = store
        self._notifier = notifier
        self._clock: Clock = clock or SystemClock()
        self._lock = threading.RLock()
        now_w, now_m = self._clock.wall(), self._clock.monotonic()
        loaded = store.load()
        self.restored = loaded is not None
        self.state = loaded or State(last_ping_wall=now_w)
        self.state.last_ping_wall = min(self.state.last_ping_wall, now_w)
        self._last_ping_mono = now_m - (now_w - self.state.last_ping_wall)
        self._started_mono = now_m
        # Qayta ishga tushgandan keyin core'ga ping yuborishga ulgurish uchun kutish:
        # soxta "jim" alerti bo'lmasligi shart.
        self._grace = (
            min(MAX_STARTUP_GRACE_S, timeout_s) if startup_grace_s is None else startup_grace_s
        )
        self._store.save(self.state)

    # -- ping qabul qilish -------------------------------------------------
    def record_ping(self, status: str = "ok", reason: str = "") -> None:
        with self._lock:
            st = self.state
            now_w, now_m = self._clock.wall(), self._clock.monotonic()
            gap = now_m - self._last_ping_mono
            if st.silent and st.pending_recovery_gap_s is None:
                st.pending_recovery_gap_s = gap
            self._last_ping_mono = now_m
            st.last_ping_wall = now_w
            if status == "degraded":
                st.degraded_streak += 1
                st.degraded_reason = reason
                st.pending_degraded_recovery = False
            else:
                st.degraded_streak = 0
                if st.degraded_alerted:
                    st.pending_degraded_recovery = True
            self._store.save(st)

    # -- qaror qabul qilish ------------------------------------------------
    def _silence_s(self) -> float:
        return self._clock.monotonic() - self._last_ping_mono

    def _next_action(self) -> _Action | None:
        with self._lock:
            st = self.state
            now_m, now_w = self._clock.monotonic(), self._clock.wall()
            silence = now_m - self._last_ping_mono

            if st.pending_recovery_gap_s is not None:
                gap = st.pending_recovery_gap_s
                text = (
                    "✅ <b>Nazoratchi core tiklandi</b>\n"
                    f"{fmt_duration(gap)} jim bo'lgan. Ping qayta kela boshladi "
                    f"({fmt_time(st.last_ping_wall)} Asia/Tashkent)."
                )

                def recovered() -> None:
                    self.state.silent = False
                    self.state.pending_recovery_gap_s = None
                    self.state.last_alert_wall = 0.0

                return _Action(text, recovered)

            if st.pending_degraded_recovery:
                text = "✅ <b>Core nosozligi tugadi</b>\nPing yana <code>ok</code> holatida keldi."

                def degraded_ok() -> None:
                    self.state.degraded_alerted = False
                    self.state.pending_degraded_recovery = False

                return _Action(text, degraded_ok)

            started_long_ago = now_m - self._started_mono >= self._grace
            if silence >= self._timeout and started_long_ago:
                last = fmt_time(st.last_ping_wall)
                if not st.silent:
                    text = (
                        "🔴 <b>Nazoratchi core javob bermayapti</b>\n"
                        f"Oxirgi ping {fmt_duration(silence)} oldin ({last} Asia/Tashkent).\n\n"
                        "Nima qilish: S-00 serverni tekshiring (RB-012)."
                    )

                    def alerted() -> None:
                        self.state.silent = True
                        self.state.last_alert_wall = self._clock.wall()
                        if self._silence_s() < self._timeout:  # yuborish paytida ping keldi
                            self.state.pending_recovery_gap_s = silence

                    return _Action(text, alerted)
                if now_w - st.last_alert_wall >= self._remind:
                    text = (
                        "🔴 <b>Nazoratchi core hali ham jim</b>\n"
                        f"{fmt_duration(silence)} dan beri ping yo'q "
                        f"(oxirgi ping {last} Asia/Tashkent).\n\n"
                        "Nima qilish: S-00 serverni tekshiring (RB-012)."
                    )

                    def reminded() -> None:
                        self.state.last_alert_wall = self._clock.wall()

                    return _Action(text, reminded)
                return None

            if st.degraded_streak >= DEGRADED_PINGS and not st.degraded_alerted:
                text = (
                    "🟠 <b>Core ishlayapti, lekin nosoz</b>\n"
                    f"Sabab: {html.escape(st.degraded_reason or 'ko‘rsatilmagan')}\n"
                    f"Ketma-ket nosoz ping: {st.degraded_streak}."
                )

                def degraded_alerted() -> None:
                    self.state.degraded_alerted = True

                return _Action(text, degraded_alerted)
            return None

    def tick(self) -> bool:
        """Kerakli xabarlarni yuboradi. False — Telegram xatosi (keyingi tsiklda qayta uriniladi)."""
        for _ in range(10):
            action = self._next_action()
            if action is None:
                return True
            if not self._notifier.send(action.text):
                return False
            with self._lock:
                action.commit()
                self._store.save(self.state)
        return True

    def run(self, stop: threading.Event, interval_s: float | None = None) -> None:
        interval = interval_s or max(0.2, min(5.0, self._timeout / 3))
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Monitor tsiklida kutilmagan xato")
            stop.wait(interval)
