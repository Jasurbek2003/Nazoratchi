from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.heartbeats.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.registry.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("", include("apps.ingest.urls")),
    path("", include("apps.metrics.urls")),
]
