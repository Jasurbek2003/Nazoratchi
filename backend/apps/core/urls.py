from django.urls import path

from . import dist, metrics_export, views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("metrics", metrics_export.metrics, name="metrics"),
    path("install.sh", dist.install_script, name="install-script"),
    path("agent/v1/<str:name>", dist.agent_file, name="agent-file"),
]
