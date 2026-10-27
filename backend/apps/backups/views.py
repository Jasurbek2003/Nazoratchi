"""Zaxira API (TZ 9.7): umumiy jadval va loyiha zaxira kartasi (FR-BKP-003)."""

from datetime import UTC, datetime
from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.http import error_response
from apps.metrics.models import SeriesLatest
from apps.registry.models import Project, ProjectServer

from . import services
from .models import BackupRun

RUNS_IN_CARD = 30  # 30 kunlik hajm grafigi


def _offsite_by_server() -> dict[Any, bool]:
    rows = SeriesLatest.objects.filter(series__name="backup_offsite_configured").select_related(
        "series"
    )
    return {r.series.server_id: r.value >= 1 for r in rows}


def _item(
    project: Project,
    links: list[ProjectServer],
    data: dict[tuple[Any, str], services.ProjectBackup],
    offsite: dict[Any, bool],
    now: datetime,
) -> dict[str, Any]:
    policy = project.backup or {}
    candidates = [
        (link, data[(link.server_id, project.slug)])
        for link in links
        if (link.server_id, project.slug) in data
    ]
    candidates.sort(key=lambda c: c[1].seen_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    link, pb = candidates[0] if candidates else (links[0] if links else None, None)
    expect = bool(policy.get("expect_daily"))
    age_hours = (now - project.created_at).total_seconds() / 3600
    state, age_h = services.status_of(pb, expect, age_hours, now)
    counts = pb.files_count or {} if pb else {}
    return {
        "project": project.slug, "project_id": str(project.pk), "name": project.name,
        "server": link.server.name if link else None, "server_id": str(link.server_id) if link else None,
        "expect_daily": expect, "expect_weekly_files": bool(policy.get("expect_weekly_files")),
        "require_offsite": bool(policy.get("require_offsite")),
        "state": state, "age_hours": round(age_h, 1) if age_h is not None else None,
        "last_success_at": datetime.fromtimestamp(pb.last_success_ts, UTC) if pb and pb.last_success_ts else None,
        "last_size_bytes": int(pb.last_size) if pb and pb.last_size is not None else None,
        "last_status": None if not pb or pb.last_status is None else ("ok" if pb.last_status >= 1 else "fail"),
        "daily_count": int(counts.get("daily", 0)), "weekly_count": int(counts.get("weekly", 0)), "files_count": int(counts.get("files", 0)),
        "newest_age_seconds": (pb.newest_age_s or {}) if pb else {},
        "offsite_configured": offsite.get(link.server_id) if link else None,
        "data_seen_at": pb.seen_at if pb else None,
    }  # fmt: skip


class BackupListView(APIView):
    """Faol, ko'chirilgan loyihalar zaxira holati: siyosati bor yoki agent ma'lumot yuborayotganlar."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        now = timezone.now()
        data = services.collect(now)
        offsite = _offsite_by_server()
        links: dict[Any, list[ProjectServer]] = {}
        for link in ProjectServer.objects.select_related("server").order_by("server__name"):
            links.setdefault(link.project_id, []).append(link)
        items = []
        for project in Project.objects.filter(status=Project.Status.ACTIVE, moved=True).order_by(
            "slug"
        ):
            plinks = links.get(project.pk, [])
            has_data = any((link.server_id, project.slug) in data for link in plinks)
            if not (project.backup or has_data):
                continue
            items.append(_item(project, plinks, data, offsite, now))
        return Response({"items": items})


class BackupDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> HttpResponse:
        project = Project.objects.filter(slug=slug).first()
        if project is None:
            return error_response("not_found", "Loyiha topilmadi.", 404)
        now = timezone.now()
        links = list(
            ProjectServer.objects.filter(project=project)
            .select_related("server")
            .order_by("server__name")
        )
        item = _item(
            project, links, services.collect(now, {project.slug}), _offsite_by_server(), now
        )
        runs = list(
            BackupRun.objects.filter(project_slug=slug).order_by("-finished_at")[:RUNS_IN_CARD]
        )
        check = services.size_check(item["server_id"], slug) if item["server_id"] else None
        item["runs"] = [
            {"finished_at": r.finished_at, "size_bytes": r.size_bytes} for r in reversed(runs)
        ]
        item["size_median_7"] = check.median if check else None
        item["size_ratio"] = round(check.ratio, 2) if check else None
        item["size_anomaly"] = bool(
            check and (check.ratio < services.SMALL_RATIO or check.ratio > services.LARGE_RATIO)
        )
        return Response(item)
