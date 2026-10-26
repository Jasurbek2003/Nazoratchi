from django.urls import path

from . import views

urlpatterns = [
    path("proto/", views.proto_page, name="proto-page"),
    path("proto/api/servers", views.servers, name="servers"),
    path("proto/api/names", views.names, name="metrics-names"),
    path("proto/api/query", views.query, name="metrics-query"),
]
