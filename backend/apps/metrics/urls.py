from django.urls import path

from . import api, views

urlpatterns = [
    path("proto/", views.proto_page, name="proto-page"),
    path("proto/api/servers", views.servers, name="servers"),
    path("proto/api/names", views.names, name="metrics-names"),
    path("proto/api/query", views.query, name="metrics-query"),
    path("api/v1/metrics/query", api.MetricsQueryView.as_view(), name="api-metrics-query"),
    path("api/v1/metrics/latest", api.MetricsLatestView.as_view(), name="api-metrics-latest"),
    path("api/v1/metrics/names", api.MetricsNamesView.as_view(), name="api-metrics-names"),
    path("api/v1/metrics/top", api.MetricsTopView.as_view(), name="api-metrics-top"),
    path(
        "api/v1/servers/<uuid:pk>/containers",
        api.ServerContainersView.as_view(),
        name="server-containers",
    ),
    path(
        "api/v1/servers/<uuid:pk>/filesystems",
        api.ServerFilesystemsView.as_view(),
        name="server-filesystems",
    ),
]
