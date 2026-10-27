"""Holatni diskda saqlash: atomik yozish (tmp + rename), 0600."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger("nazoratchi_watchdog.state")


@dataclass
class State:
    last_ping_wall: float
    silent: bool = False  # "jim" alerti yuborilgan, tiklanish xabari hali yuborilmagan
    last_alert_wall: float = 0.0
    degraded_streak: int = 0
    degraded_alerted: bool = False
    degraded_reason: str = ""
    pending_recovery_gap_s: float | None = None
    pending_degraded_recovery: bool = False


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> State | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log.warning("Holat fayli o'qilmadi, yangi holat bilan boshlanadi: %s", exc)
            return None
        try:
            if not isinstance(raw, dict):
                raise TypeError("ob'ekt kutilgan")
            known = {f.name for f in fields(State)}
            state = State(**{k: v for k, v in raw.items() if k in known})
            ping = state.last_ping_wall
            if isinstance(ping, bool) or not isinstance(ping, int | float):
                raise TypeError("last_ping_wall son emas")
            state.last_ping_wall = float(ping)
        except (TypeError, ValueError) as exc:
            log.warning("Holat fayli yaroqsiz, yangi holat bilan boshlanadi: %s", exc)
            return None
        return state

    def save(self, state: State) -> bool:
        data = json.dumps(asdict(state), ensure_ascii=False).encode("utf-8")
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("Holat fayliga yozib bo'lmadi: %s", exc)
            with contextlib.suppress(OSError):
                tmp.unlink()
            return False
        return True
