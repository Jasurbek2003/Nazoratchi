"""RBAC (TZ 3.2, 14.4). Bu modul `rest_framework.views` ni import qilmaydi: DRF sozlamasi uni view'lardan
oldin yuklaydi (aylanma import bo'lmasligi uchun)."""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class DenyByDefault(BasePermission):
    """E'lon qilinmagan endpoint rad etiladi (TZ 14.4): har view o'z ruxsatini aniq belgilashi shart."""

    message = "Bu endpoint uchun ruxsat e'lon qilinmagan."

    def has_permission(self, request: Request, view: Any) -> bool:
        return False


def roles(*allowed: str) -> type[BasePermission]:
    """`permission_classes = [IsAuthenticated, roles("owner", "operator")]` shaklida ishlatiladi."""

    class HasRole(BasePermission):
        message = "Sizning rolingiz bu amalga ruxsat bermaydi."

        def has_permission(self, request: Request, view: Any) -> bool:
            user = request.user
            return bool(user and user.is_authenticated and getattr(user, "role", None) in allowed)

    HasRole.__name__ = "HasRole_" + "_".join(allowed)
    return HasRole
