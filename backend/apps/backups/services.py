"""Zaxira tarixini yuritish va holatni hisoblash (FR-BKP-002..005, 010)."""

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apps.metrics.models import SeriesLatest

from .models import BackupRun

AGENT_FRESH_S = (
    15 * 60
)  # agent zaxira metrikalarini 5 daqiqada yuboradi; 15 daqiqadan eskisi "agent jim"
LATE_HOURS = 26  # FR-BKP-004
CRITICAL_HOURS = 50
ANOMALY_HISTORY = 7  # FR-BKP-005: oldingi 7 zaxira medianasi
SMALL_RATIO = 0.5
LARGE_RATIO = 3.0
BACKUP_METRICS = (
    "backup_last_status",
    "backup_last_success_timestamp",
    "backup_last_size_bytes",
    "backup_newest_file_age_seconds",
    "backup_files_count",
    "backup_offsite_configured",
)


@dataclass
class ProjectBackup:
    """Bir loyihaning (bir serverdagi) zaxira holati agent metrikalaridan."""

    server_id: Any
    project: str
    last_status: float | None = None
    last_success_ts: float | None = None
    last_size: float | None = None
    newest_age_s: dict[str, float] | None = None
    files_count: dict[str, float] | None = None
    seen_at: datetime | None = None  # eng yangi namuna vaqti (agent tirikligi)


def collect(
    now: datetime, project_slugs: set[str] | None = None
) -> dict[tuple[Any, str], ProjectBackup]:
    """{(server_id, loyiha): ProjectBackup} — barcha `backup_*` seriyalarning oxirgi qiymatlari (bitta so'rov)."""
    rows = SeriesLatest.objects.filter(series__name__in=BACKUP_METRICS).select_related("series")
    out: dict[tuple[Any, str], ProjectBackup] = {}
    for row in rows:
        slug = row.series.labels.get("project", "")
        if not slug or (project_slugs is not None and slug not in project_slugs):
            continue
        pb = out.setdefault(
            (row.series.server_id, slug),
            ProjectBackup(row.series.server_id, slug, newest_age_s={}, files_count={}),
        )
        name, kind = row.series.name, row.series.labels.get("kind", "")
        if name == "backup_last_status":
            pb.last_status = row.value
        elif name == "backup_last_success_timestamp":
            pb.last_success_ts = row.value
        elif name == "backup_last_size_bytes":
            pb.last_size = row.value
        elif name == "backup_newest_file_age_seconds" and pb.newest_age_s is not None:
            pb.newest_age_s[kind] = row.value
        elif name == "backup_files_count" and pb.files_count is not None:
            pb.files_count[kind] = row.value
        if pb.seen_at is None or row.time > pb.seen_at:
            pb.seen_at = row.time
    return out


def agent_alive(pb: ProjectBackup, now: datetime) -> bool:
    return pb.seen_at is not None and (now - pb.seen_at).total_seconds() <= AGENT_FRESH_S


def sync_runs(now: datetime) -> int:
    """Yangi muvaffaqiyatli zaxiralarni `BackupRun` ga yozadi. Qaytadi: yaratilganlar soni. Idempotent."""
    created = 0
    for (server_id, slug), pb in collect(now).items():
        if pb.last_success_ts is None:
            continue
        finished = datetime.fromtimestamp(pb.last_success_ts, UTC)
        _, made = BackupRun.objects.get_or_create(
            server_id=server_id, project_slug=slug, kind=BackupRun.Kind.DAILY, finished_at=finished,
            defaults={"size_bytes": int(pb.last_size or 0)},
        )  # fmt: skip
        created += made
    return created


@dataclass
class SizeCheck:
    latest: int
    median: float
    ratio: float
    finished_at: datetime


def size_check(server_id: Any, slug: str) -> SizeCheck | None:
    """Eng yangi zaxira hajmi va oldingi 7 tasi medianasi. Tarix yetarli bo'lmasa (< 8 ta) None (FR-BKP-005:
    birinchi 7 kunda faqat ma'lumot)."""
    runs = list(
        BackupRun.objects.filter(server_id=server_id, project_slug=slug, kind=BackupRun.Kind.DAILY)
        .order_by("-finished_at")[: ANOMALY_HISTORY + 1]
    )  # fmt: skip
    if len(runs) < ANOMALY_HISTORY + 1:
        return None
    median = statistics.median(r.size_bytes for r in runs[1:])
    if median <= 0:
        return None
    return SizeCheck(runs[0].size_bytes, median, runs[0].size_bytes / median, runs[0].finished_at)


def status_of(
    pb: ProjectBackup | None, expect_daily: bool, project_age_h: float, now: datetime
) -> tuple[str, float | None]:
    """(holat, yosh soatda). Holat: ok, late (>26 s), critical (>50 s), failed, stale (agent jim), missing
    (kutilgan, lekin hech qachon yo'q), none (zaxira kutilmaydi)."""
    if pb is None or pb.last_success_ts is None:
        if not expect_daily:
            return "none", None
        return ("missing" if project_age_h >= LATE_HOURS else "unknown"), None
    age_h = (now.timestamp() - pb.last_success_ts) / 3600
    if not agent_alive(pb, now):
        return "stale", age_h
    if pb.last_status == 0:
        return "failed", age_h
    if age_h > CRITICAL_HOURS:
        return "critical", age_h
    if age_h > LATE_HOURS:
        return "late", age_h
    return "ok", age_h
