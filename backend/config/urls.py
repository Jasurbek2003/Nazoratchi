from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.ingest.urls")),
    path("", include("apps.metrics.urls")),
]
