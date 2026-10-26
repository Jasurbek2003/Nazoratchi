"""Metrikalarni bazaga yozish (TZ 6.5.1): series aniqlash va `unnest` bilan paketli yozuv."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from apps.metrics.models import Series
from apps.registry.models import Server

from .catalog import (
    MAX_CLOCK_SKEW_S,
    MAX_FUTURE_S,
    MAX_SAMPLE_AGE_S,
    MAX_SERIES_PER_HOST,
    ROLLUP_METRICS,
    kind_for,
    unit_for,
)
from .validation import Sample, parse_sample

SeriesKey = tuple[str, str]  # (nom, labels_hash)


def labels_hash(labels: dict[str, str]) -> str:
    canonical = json.dumps(labels, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(canonical.encode(), usedforsecurity=False).hexdigest()


@dataclass
class IngestResult:
    accepted: int = 0
    rejected: int = 0
    duplicate: bool = False
    clock_skew: bool = False
    series_dropped: int = 0
    reasons: dict[str, int] = field(default_factory=dict)


def _series_map(server: Server) -> dict[SeriesKey, int]:
    return {
        (name, h): pk
        for pk, name, h in Series.objects.filter(server=server).values_list(
            "id", "name", "labels_hash"
        )
    }


def _resolve_series(server: Server, samples: list[Sample], result: IngestResult) -> dict[int, int]:
    """Namunalar indeksi -> series_id. Kardinallik chegarasidan oshganlari tashlanadi."""
    known = _series_map(server)
    fresh: dict[SeriesKey, Sample] = {}
    for sample in samples:
        key = (sample.name, labels_hash(sample.labels))
        if key not in known and key not in fresh:
            if len(known) + len(fresh) >= MAX_SERIES_PER_HOST:
                continue
            fresh[key] = sample
    if fresh:
        Series.objects.bulk_create(
            [
                Series(
                    server=server,
                    name=s.name,
                    labels=s.labels,
                    labels_hash=h,
                    unit=unit_for(s.name),
                    kind=kind_for(s.name),
                    rollup=s.name in ROLLUP_METRICS,
                )
                for (_, h), s in fresh.items()
            ],
            ignore_conflicts=True,
        )
        known = _series_map(server)
    mapping: dict[int, int] = {}
    for idx, sample in enumerate(samples):
        pk = known.get((sample.name, labels_hash(sample.labels)))
        if pk is None:
            result.series_dropped += 1
        else:
            mapping[idx] = pk
    return mapping


def ingest_batch(
    server: Server, raw_samples: list[Any], sent_at: datetime, now: datetime | None = None
) -> IngestResult:
    now = now or timezone.now()
    result = IngestResult()

    samples: list[Sample] = []
    for raw in raw_samples:
        sample = parse_sample(raw)
        if sample is None:
            result.rejected += 1
        else:
            samples.append(sample)

    # Agent soati siljishi `sent_at` orqali aniqlanadi (TZ 6.10): siljigan bo'lsa butun paket vaqti
    # farqqa tuzatiladi. Aks holda namuna vaqti saqlanadi, shunda 15 daqiqalik bufer (FR-AGT-007)
    # kechikib yetkazilsa ham buzilmaydi.
    offset = now - sent_at
    result.clock_skew = abs(offset) > timedelta(seconds=MAX_CLOCK_SKEW_S)
    shift = offset if result.clock_skew else timedelta(0)
    oldest = now - timedelta(seconds=MAX_SAMPLE_AGE_S)
    newest = now + timedelta(seconds=MAX_FUTURE_S)
    kept: list[Sample] = []
    times: list[datetime] = []
    for sample in samples:
        t = datetime.fromtimestamp(sample.t_ms / 1000, UTC) + shift
        if t < oldest or t > newest:
            result.rejected += 1
            continue
        kept.append(sample)
        times.append(t)
    samples = kept

    with transaction.atomic():
        mapping = _resolve_series(server, samples, result)
        rows = [(times[i], sid, samples[i].value) for i, sid in mapping.items()]
        result.rejected += result.series_dropped
        if rows:
            inserted = _write_samples(rows)
            result.accepted = len(rows)
            # Hech narsa yozilmagan bo'lsa, paket avval qabul qilingan (idempotent qayta yuborish).
            result.duplicate = inserted == 0
    return result


def _write_samples(rows: list[tuple[datetime, int, float]]) -> int:
    times = [r[0] for r in rows]
    series_ids = [r[1] for r in rows]
    values = [r[2] for r in rows]
    # Bir paketda bir xil (series_id, time) bo'lsa, oxirgisi qoladi.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO metric_samples (time, series_id, value)
            SELECT * FROM unnest(%s::timestamptz[], %s::bigint[], %s::double precision[])
            ON CONFLICT (series_id, time) DO NOTHING
            """,
            [times, series_ids, values],
        )
        inserted = cursor.rowcount
        # Eng oxirgi qiymat: faqat yangiroq bo'lsa yangilanadi (eski paket qayta kelsa buzmasin).
        cursor.execute(
            """
            INSERT INTO metrics_serieslatest (series_id, time, value)
            SELECT DISTINCT ON (s) s, t, v
            FROM unnest(%s::bigint[], %s::timestamptz[], %s::double precision[]) AS x(s, t, v)
            ORDER BY s, t DESC
            ON CONFLICT (series_id) DO UPDATE
                SET time = EXCLUDED.time, value = EXCLUDED.value
                WHERE EXCLUDED.time >= metrics_serieslatest.time
            """,
            [series_ids, times, values],
        )
        cursor.execute(
            "UPDATE metrics_series SET last_seen = %s WHERE id = ANY(%s)",
            [times[-1], list(set(series_ids))],
        )
    return int(inserted)
