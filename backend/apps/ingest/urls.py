from django.urls import path

from . import views

urlpatterns = [
    path("ingest/v1/enroll", views.enroll, name="ingest-enroll"),
    path("ingest/v1/metrics", views.ingest_metrics, name="ingest-metrics"),
    path("ingest/v1/goodbye", views.goodbye, name="ingest-goodbye"),
]
