"""Loyihalar va domenlar (TZ 9.4, FR-REG-002..006, 010): CRUD, serverga biriktirish, port to'qnashuvi, arxiv."""

import re
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.permissions import roles

from .models import Domain, Project, ProjectServer, Server

WRITERS: list[type[BasePermission]] = [IsAuthenticated, roles("owner", "operator")]
OWNER: list[type[BasePermission]] = [IsAuthenticated, roles("owner")]
PORT_RANGE = (1024, 65535)
MAX_PORTS = 10
APP_PORTS = range(
    8000, 9000
)  # asosiy port oralig'i; yordamchi: 3000..3999 (REGISTRY.md qoidasidan)
AUX_PORTS = range(3000, 4000)
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_fqdn(value: str) -> str:
    fqdn = value.strip().lower().rstrip(".")
    labels = fqdn.split(".")
    if (
        len(fqdn) > 253
        or len(labels) < 2
        or not all(_LABEL.match(x) for x in labels)
        or labels[-1].isdigit()
    ):
        raise serializers.ValidationError("Domen nomi noto'g'ri (masalan, app.example.uz).")
    return fqdn


# ----------------------------------------------------------------------- serializerlar
class DomainSerializer(serializers.ModelSerializer[Domain]):
    project_slug = serializers.CharField(source="project.slug", read_only=True, default=None)
    auto_probes = serializers.BooleanField(write_only=True, required=False, default=True)

    class Meta:
        model = Domain
        fields = [
            "id", "project", "project_slug", "fqdn", "expected_ips", "dns_provider", "registrar",
            "controlled_by", "tls_enabled", "status", "notes", "created_at", "auto_probes",
        ]  # fmt: skip
        read_only_fields = ["id", "created_at"]
        extra_kwargs: dict[str, Any] = {"fqdn": {"validators": []}}  # noyoblik view'da (409)

    def validate_fqdn(self, value: str) -> str:
        return normalize_fqdn(value)


class ProjectSerializer(serializers.ModelSerializer[Project]):
    servers_info = serializers.SerializerMethodField()
    domains_info = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "slug", "name", "description", "owner_name", "owner_contact", "kind", "moved", "status",
            "tags", "links", "notes", "created_at", "updated_at", "servers_info", "domains_info",
        ]  # fmt: skip
        read_only_fields = ["id", "status", "created_at", "updated_at"]
        extra_kwargs: dict[str, Any] = {"slug": {"validators": []}}

    def validate_slug(self, value: str) -> str:
        from .models import slug_validator

        slug_validator(value)
        return value

    def get_servers_info(self, obj: Project) -> list[dict[str, Any]]:
        rows = (
            ProjectServer.objects.filter(project=obj)
            .select_related("server")
            .order_by("server__name")
        )
        return [
            {
                "server_id": str(r.server_id),
                "server": r.server.name,
                "environment": r.environment,
                "ports": r.ports,
            }
            for r in rows
        ]

    def get_domains_info(self, obj: Project) -> list[dict[str, Any]]:
        domains = obj.domains.exclude(status=Domain.Status.ARCHIVED).order_by("fqdn")
        return [{"id": str(d.pk), "fqdn": d.fqdn, "status": d.status} for d in domains]


class ProjectServerSerializer(serializers.Serializer[Any]):
    server_id = serializers.UUIDField()
    environment = serializers.ChoiceField(
        choices=ProjectServer.Environment.choices, default="production"
    )
    ports = serializers.ListField(
        child=serializers.IntegerField(min_value=PORT_RANGE[0], max_value=PORT_RANGE[1]),
        required=False, default=list, max_length=MAX_PORTS,
    )  # fmt: skip


# ----------------------------------------------------------------------- portlar
def used_ports(server_id: str | UUID, exclude_project: UUID | None = None) -> dict[int, str]:
    """Serverdagi band portlar -> loyiha slug (faol loyihalar)."""
    rows = ProjectServer.objects.filter(
        server_id=server_id, project__status=Project.Status.ACTIVE
    ).select_related("project")
    if exclude_project is not None:
        rows = rows.exclude(project=exclude_project)
    return {port: r.project.slug for r in rows for port in r.ports}


def next_ports(server_id: str | UUID) -> list[int]:
    """Keyingi bo'sh port juftligi: 8000..8999 dan eng kichigi va unga mos 3xxx (band bo'lsa — eng kichik bo'sh)."""
    used = set(used_ports(server_id))
    app = next((p for p in APP_PORTS if p not in used), None)
    if app is None:
        return []
    twin = 3000 + (app - 8000)
    aux = twin if twin not in used else next((p for p in AUX_PORTS if p not in used), None)
    return [app] if aux is None else [app, aux]


def port_conflicts(entries: list[dict[str, Any]], project: Project | None) -> list[dict[str, str]]:
    """Yangi biriktirishlar uchun to'qnashuvlar (boshqa loyihalar bilan va ro'yxat ichida)."""
    problems: list[dict[str, str]] = []
    seen: dict[tuple[str, int], int] = {}
    for entry in entries:
        sid = str(entry["server_id"])
        taken = used_ports(sid, exclude_project=project.pk if project else None)
        for port in entry["ports"]:
            if port in taken:
                free = next_ports(sid)
                problems.append(
                    {
                        "field": "servers", "code": "port_in_use",
                        "message": f"{port} port '{taken[port]}' loyihasida band. Keyingi bo'sh: {free}",
                    }
                )  # fmt: skip
            elif (sid, port) in seen:
                problems.append(
                    {
                        "field": "servers",
                        "code": "port_duplicate",
                        "message": f"{port} port ro'yxatda ikki marta.",
                    }
                )
            seen[(sid, port)] = 1
    return problems


def _validate_servers(raw: Any) -> list[dict[str, Any]]:
    serializer = ProjectServerSerializer(data=raw, many=True)
    serializer.is_valid(raise_exception=True)
    entries = [dict(e) for e in serializer.validated_data]
    ids = {e["server_id"] for e in entries}
    found = set(
        Server.objects.filter(pk__in=ids)
        .exclude(status=Server.Status.ARCHIVED)
        .values_list("pk", flat=True)
    )
    if missing := ids - found:
        raise serializers.ValidationError(
            {"servers": f"Server topilmadi: {', '.join(sorted(map(str, missing)))}"}
        )
    keys = [(e["server_id"], e["environment"]) for e in entries]
    if len(keys) != len(set(keys)):
        raise serializers.ValidationError(
            {"servers": "Bir server + muhit juftligi ikki marta berilgan."}
        )
    return entries


def set_servers(project: Project, entries: list[dict[str, Any]]) -> None:
    ProjectServer.objects.filter(project=project).delete()
    ProjectServer.objects.bulk_create(
        [
            ProjectServer(
                project=project,
                server_id=e["server_id"],
                environment=e["environment"],
                ports=list(dict.fromkeys(e["ports"])),
            )
            for e in entries
        ]
    )


def _auto_probes(domain: Domain) -> None:
    from apps.probes.services import ensure_domain_probes

    ensure_domain_probes(domain)


# ----------------------------------------------------------------------- loyihalar
class ProjectListView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "POST" else [IsAuthenticated])]

    def get(self, request: Request) -> Response:
        q = request.query_params
        rows = Project.objects.all()
        rows = (
            rows.filter(status=q["status"])
            if q.get("status")
            else rows.exclude(status=Project.Status.ARCHIVED)
        )
        if text := q.get("q"):
            rows = rows.filter(
                Q(name__icontains=text) | Q(slug__icontains=text) | Q(domains__fqdn__icontains=text)
            ).distinct()
        if tag := q.get("tag"):
            rows = rows.filter(tags__contains=[tag])
        if server_id := q.get("server_id"):
            rows = rows.filter(projectserver__server_id=server_id).distinct()
        if q.get("moved") in ("true", "false"):
            rows = rows.filter(moved=q["moved"] == "true")
        return Response({"items": ProjectSerializer(rows.order_by("slug"), many=True).data})

    def post(self, request: Request) -> HttpResponse:
        data = request.data if isinstance(request.data, dict) else {}
        serializer = ProjectSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        entries = _validate_servers(data.get("servers", [])) if data.get("servers") else []
        domain_rows = data.get("domains", [])
        if not isinstance(domain_rows, list):
            raise serializers.ValidationError({"domains": "Ro'yxat bo'lishi kerak."})
        if problems := port_conflicts(entries, None):
            return error_response("port_conflict", "Port to'qnashuvi.", 409, details=problems)
        auto = data.get("auto_probes", True) is not False
        try:
            with transaction.atomic():
                project = Project.objects.create(**serializer.validated_data)
                set_servers(project, entries)
                domains = []
                for row in domain_rows:
                    ds = DomainSerializer(data={**row, "project": project.pk})
                    ds.is_valid(raise_exception=True)
                    domains.append(
                        Domain.objects.create(
                            **{k: v for k, v in ds.validated_data.items() if k != "auto_probes"}
                        )
                    )
                if auto and project.moved:
                    for d in domains:
                        _auto_probes(d)
        except IntegrityError:
            return error_response("duplicate", "Bunday slug yoki domen allaqachon mavjud.", 409)
        record(
            "project.create",
            request=request._request,
            object_type="project",
            object_id=project.pk,
            after=ProjectSerializer(project).data,
        )
        return Response(ProjectSerializer(project).data, status=201)


class ProjectDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "PATCH" else [IsAuthenticated])]

    def get(self, request: Request, pk: str) -> HttpResponse:
        project = Project.objects.filter(pk=pk).first()
        return (
            Response(ProjectSerializer(project).data)
            if project
            else error_response("not_found", "Loyiha topilmadi.", 404)
        )

    def patch(self, request: Request, pk: str) -> HttpResponse:
        project = Project.objects.filter(pk=pk).exclude(status=Project.Status.ARCHIVED).first()
        if project is None:
            return error_response("not_found", "Loyiha topilmadi.", 404)
        data = {
            k: v
            for k, v in (request.data if isinstance(request.data, dict) else {}).items()
            if k != "slug"
        }
        before = ProjectSerializer(project).data
        serializer = ProjectSerializer(project, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record(
            "project.update",
            request=request._request,
            object_type="project",
            object_id=project.pk,
            before=before,
            after=serializer.data,
        )
        return Response(serializer.data)


class ProjectArchiveView(APIView):
    """Arxivlash: tarix saqlanadi, tekshiruvlar to'xtaydi (alert yo'q)."""

    permission_classes = OWNER

    def post(self, request: Request, pk: str) -> HttpResponse:
        from apps.probes.models import Probe

        project = Project.objects.filter(pk=pk).exclude(status=Project.Status.ARCHIVED).first()
        if project is None:
            return error_response("not_found", "Loyiha topilmadi.", 404)
        with transaction.atomic():
            project.status = Project.Status.ARCHIVED
            project.save(update_fields=["status", "updated_at"])
            Probe.objects.filter(project=project).update(enabled=False)
        record(
            "project.archive", request=request._request, object_type="project", object_id=project.pk
        )
        return Response(ProjectSerializer(project).data)


class ProjectServersView(APIView):
    """`PUT /projects/{id}/servers`: serverlarga biriktirishni to'liq almashtiradi; port to'qnashuvida 409."""

    permission_classes = WRITERS

    def put(self, request: Request, pk: str) -> HttpResponse:
        project = Project.objects.filter(pk=pk).exclude(status=Project.Status.ARCHIVED).first()
        if project is None:
            return error_response("not_found", "Loyiha topilmadi.", 404)
        entries = _validate_servers(request.data)
        if problems := port_conflicts(entries, project):
            return error_response("port_conflict", "Port to'qnashuvi.", 409, details=problems)
        before = ProjectSerializer(project).data["servers_info"]
        with transaction.atomic():
            set_servers(project, entries)
        after = ProjectSerializer(project).data["servers_info"]
        record(
            "project.servers",
            request=request._request,
            object_type="project",
            object_id=project.pk,
            before={"servers": before},
            after={"servers": after},
        )
        return Response({"servers": after})


class NextPortsView(APIView):
    permission_classes = WRITERS

    def get(self, request: Request) -> HttpResponse:
        server_id = request.query_params.get("server_id", "")
        if (
            not Server.objects.filter(pk=server_id).exists()
            if re.fullmatch(r"[0-9a-fA-F-]{36}", server_id)
            else True
        ):
            return error_response("validation_error", "server_id (mavjud server) majburiy.", 400)
        return Response({"server_id": server_id, "ports": next_ports(server_id)})


# ----------------------------------------------------------------------- domenlar
class DomainListView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "POST" else [IsAuthenticated])]

    def get(self, request: Request) -> Response:
        q = request.query_params
        rows = Domain.objects.select_related("project")
        rows = (
            rows.filter(status=q["status"])
            if q.get("status")
            else rows.exclude(status=Domain.Status.ARCHIVED)
        )
        if project_id := q.get("project_id"):
            rows = rows.filter(project_id=project_id)
        if text := q.get("q"):
            rows = rows.filter(fqdn__icontains=text.lower())
        return Response({"items": DomainSerializer(rows.order_by("fqdn"), many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = DomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        auto = data.pop("auto_probes", True)
        if Domain.objects.filter(fqdn=data["fqdn"]).exists():
            return error_response("duplicate", "Bunday domen mavjud.", 409)
        with transaction.atomic():
            domain = Domain.objects.create(**data)
            project = domain.project
            if (
                auto
                and project is not None
                and project.moved
                and project.status == Project.Status.ACTIVE
            ):
                _auto_probes(domain)
        record(
            "domain.create",
            request=request._request,
            object_type="domain",
            object_id=domain.pk,
            after=DomainSerializer(domain).data,
        )
        return Response(DomainSerializer(domain).data, status=201)


class DomainDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "PATCH" else [IsAuthenticated])]

    def get(self, request: Request, pk: str) -> HttpResponse:
        domain = Domain.objects.select_related("project").filter(pk=pk).first()
        return (
            Response(DomainSerializer(domain).data)
            if domain
            else error_response("not_found", "Domen topilmadi.", 404)
        )

    def patch(self, request: Request, pk: str) -> HttpResponse:
        domain = Domain.objects.select_related("project").filter(pk=pk).first()
        if domain is None:
            return error_response("not_found", "Domen topilmadi.", 404)
        before = DomainSerializer(domain).data
        serializer = DomainSerializer(domain, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if (
            "fqdn" in serializer.validated_data
            and Domain.objects.filter(fqdn=serializer.validated_data["fqdn"])
            .exclude(pk=domain.pk)
            .exists()
        ):
            return error_response("duplicate", "Bunday domen mavjud.", 409)
        serializer.save()
        if "expected_ips" in serializer.validated_data and domain.status == Domain.Status.ACTIVE:
            from apps.probes.services import sync_dns_probe

            sync_dns_probe(domain)
        if domain.status == Domain.Status.ARCHIVED:  # FR-REG-006: arxivlangan alert yubormaydi
            from apps.probes.models import Probe

            Probe.objects.filter(domain=domain).update(enabled=False)
        record(
            "domain.update",
            request=request._request,
            object_type="domain",
            object_id=domain.pk,
            before=before,
            after=serializer.data,
        )
        return Response(serializer.data)
