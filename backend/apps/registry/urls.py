from django.urls import path

from . import views

urlpatterns = [
    path("servers/", views.ServerListView.as_view(), name="servers"),
    path("servers/<uuid:pk>", views.ServerDetailView.as_view(), name="server"),
    path(
        "servers/<uuid:pk>/enroll-token",
        views.ServerEnrollTokenView.as_view(),
        name="server-enroll-token",
    ),
]
