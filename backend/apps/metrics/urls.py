from django.urls import path

from . import views

urlpatterns = [
    path("proto/", views.proto_page, name="proto-page"),
    path("api/v1/servers", views.servers, name="servers"),
    path("api/v1/metrics/names", views.names, name="metrics-names"),
    path("api/v1/metrics/query", views.query, name="metrics-query"),
]
