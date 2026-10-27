"""Core'ga yuborish (TZ 7.5.2): gzip JSON, Bearer token, xato kodlariga ko'ra xatti-harakat."""

import gzip
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

VERSION = "proto-agent/0.1.0"

Outcome = Literal["ok", "drop", "retry"]


@dataclass
class Batch:
    batch_id: str
    seq: int
    samples: list[dict[str, Any]]
    facts: dict[str, Any] = field(default_factory=dict)
    created: float = 0.0  # monotonic; bufer yoshini hisoblash uchun


@dataclass
class SendResult:
    outcome: Outcome
    status: int | None = None
    retry_after: float | None = None
    detail: str = ""
    response: dict[str, Any] = field(default_factory=dict)


def build_payload(batch: Batch, now: datetime | None = None) -> dict[str, Any]:
    """`sent_at` har yuborishda yangilanadi: core shu bilan agent soati siljishini aniqlaydi."""
    sent_at = (now or datetime.now(UTC)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "batch_id": batch.batch_id,
        "seq": batch.seq,
        "sent_at": sent_at,
        "samples": batch.samples,
    }
    if batch.facts:
        payload["facts"] = batch.facts
    return payload


@dataclass
class Enrolled:
    host_id: str
    agent_token: str
    interval_seconds: int


class EnrollError(Exception):
    """Enroll rad etildi yoki core'ga ulanib bo'lmadi. `code` — core xato kodi (TZ 7.5.1)."""

    def __init__(self, code: str, status: int | None = None) -> None:
        super().__init__(f"{code} (HTTP {status})" if status else code)
        self.code = code
        self.status = status


def enroll(url: str, enroll_token: str, facts: dict[str, Any], timeout: float = 10.0) -> Enrolled:
    """Bir martalik enroll token -> doimiy agent tokeni (TZ 7.5.1)."""
    body = json.dumps(
        {
            "enroll_token": enroll_token,
            "hostname": facts.get("hostname", ""),
            "agent_version": VERSION,
            "facts": facts,
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310 (url operator sozlamasidan)
        url.rstrip("/") + "/ingest/v1/enroll",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Nazoratchi-Agent": VERSION},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            code = json.loads(exc.read())["error"]["code"]
        except (ValueError, KeyError, TypeError):
            code = "http_error"
        raise EnrollError(str(code), exc.code) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise EnrollError(f"ulanib bo'lmadi: {exc}") from exc
    try:
        return Enrolled(
            str(data["host_id"]), str(data["agent_token"]), int(data["interval_seconds"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EnrollError("javob noto'g'ri") from exc


class Sender:
    def __init__(self, url: str, token: str, timeout: float = 10.0) -> None:
        self.endpoint = url.rstrip("/") + "/ingest/v1/metrics"
        self._token = token
        self.timeout = timeout

    def send(self, batch: Batch) -> SendResult:
        body = gzip.compress(json.dumps(build_payload(batch)).encode())
        request = urllib.request.Request(  # noqa: S310 (url operator sozlamasidan)
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "X-Nazoratchi-Agent": VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                data = json.loads(response.read() or b"{}")
                return SendResult("ok", response.status, response=data)
        except urllib.error.HTTPError as exc:
            return self._classify(exc)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            return SendResult("retry", None, detail=str(exc))

    @staticmethod
    def _classify(exc: urllib.error.HTTPError) -> SendResult:
        status = exc.code
        if status in (400, 413):
            # Paket yaroqsiz: navbatda qoldirmaymiz (TZ 7.5.2), aks holda abadiy takrorlanadi.
            return SendResult("drop", status, detail=f"HTTP {status}")
        if status == 401:
            # Token bekor qilingan bo'lishi mumkin: 5 daqiqa kutib qayta uriniladi.
            return SendResult("retry", status, retry_after=300.0, detail="HTTP 401")
        if status == 429:
            header = exc.headers.get("Retry-After", "")
            return SendResult(
                "retry", status, retry_after=float(header) if header.isdigit() else 30.0
            )
        return SendResult("retry", status, detail=f"HTTP {status}")
