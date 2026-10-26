"""Prototip agent: har `interval` soniyada yig'adi va yuboradi (FR-AGT-004..007).

Bufer prototipda xotirada (maks. 15 daqiqa); F1 Go agentida diskda (20 MB) bo'ladi.
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable

from .collectors import Collector, host_facts
from .sender import Batch, Sender, SendResult

BUFFER_MAX_AGE_S = 15 * 60
BACKOFF_STEPS = (1, 2, 4, 8, 16, 30)  # TZ 7.2 Sender


class Agent:
    def __init__(
        self,
        collector: Collector,
        sender: Sender,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print,
    ) -> None:
        self.collector = collector
        self.sender = sender
        self.clock = clock
        self.log = log
        self.queue: deque[Batch] = deque()
        self.seq = 0
        self.failures = 0
        self.next_attempt = 0.0
        self._facts_sent = False
        self._prefix = uuid.uuid4().hex[:8]

    def tick(self) -> None:
        """Bir davr: yig'ish -> navbatga -> yuborishga urinish."""
        self.seq += 1
        batch = Batch(
            batch_id=f"b-{self._prefix}-{self.seq}",
            seq=self.seq,
            samples=self.collector.collect(),
            facts={} if self._facts_sent else host_facts(),
            created=self.clock(),
        )
        self._facts_sent = True
        self.queue.append(batch)
        self._drop_expired()
        self.flush()

    def _drop_expired(self) -> None:
        while self.queue and self.clock() - self.queue[0].created > BUFFER_MAX_AGE_S:
            old = self.queue.popleft()
            self.log(f"bufer to'ldi: {old.batch_id} tashlandi (15 daqiqadan eski)")

    def flush(self) -> None:
        """Navbatni vaqt tartibida bo'shatadi; xatoda to'xtaydi va keyingi davrni kutadi."""
        while self.queue and self.clock() >= self.next_attempt:
            batch = self.queue[0]
            result = self.sender.send(batch)
            if result.outcome == "ok":
                self.queue.popleft()
                self.failures = 0
                self.log(_ok_line(batch, result))
                continue
            if result.outcome == "drop":
                self.queue.popleft()
                self.log(f"paket rad etildi ({result.detail}): {batch.batch_id}")
                continue
            self.failures += 1
            self.next_attempt = self.clock() + self._backoff(result)
            self.log(
                f"yuborilmadi ({result.detail}); navbat: {len(self.queue)}; keyin qayta uriniladi"
            )
            return

    def _backoff(self, result: SendResult) -> float:
        if result.retry_after is not None:
            return result.retry_after
        step = BACKOFF_STEPS[min(self.failures - 1, len(BACKOFF_STEPS) - 1)]
        return step * random.uniform(0.9, 1.1)  # noqa: S311 (jitter, kriptografiya emas)


def _ok_line(batch: Batch, result: SendResult) -> str:
    data = result.response
    return (
        f"yuborildi {batch.batch_id}: qabul={data.get('accepted')} rad={data.get('rejected')}"
        f"{' SOAT-SILJISHI' if data.get('clock_skew') else ''}"
    )


def run(
    agent: Agent, interval: float, count: int = 0, sleep: Callable[[float], None] = time.sleep
) -> None:
    n = 0
    while count == 0 or n < count:
        started = time.monotonic()
        agent.tick()
        n += 1
        if count and n >= count:
            break
        sleep(max(0.0, interval - (time.monotonic() - started)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nazoratchi prototip agenti")
    parser.add_argument("--url", default=os.environ.get("NAZORATCHI_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.environ.get("NAZORATCHI_TOKEN", ""))
    parser.add_argument("--interval", type=float, default=15.0, help="soniya (standart 15)")
    parser.add_argument(
        "--count", type=int, default=0, help="shuncha davrdan keyin to'xtash (0 = cheksiz)"
    )
    parser.add_argument("--dry-run", action="store_true", help="yubormasdan JSON chiqarish")
    args = parser.parse_args(argv)

    if args.dry_run:
        collector = Collector()
        time.sleep(1.0)
        print(json.dumps({"facts": host_facts(), "samples": collector.collect()}, indent=2))
        return 0
    if not args.token:
        print("token kerak: --token yoki NAZORATCHI_TOKEN", file=sys.stderr)
        return 2
    agent = Agent(Collector(), Sender(args.url, args.token))
    try:
        run(agent, args.interval, args.count)
    except KeyboardInterrupt:
        print("to'xtatildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
