from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed(sender: Any, **kwargs: Any) -> None:
    """Toza o'rnatishda standart qoidalar tayyor bo'ladi (FR-ALR-006)."""
    from .catalog import sync_built_in

    sync_built_in()


class AlertsConfig(AppConfig):
    name = "apps.alerts"
    label = "alerts"

    def ready(self) -> None:
        post_migrate.connect(_seed, sender=self, dispatch_uid="alerts_seed_rules")
