from django.urls import path

from . import views

urlpatterns = [
    path("ingest/v1/metrics", views.ingest_metrics, name="ingest-metrics"),
]
