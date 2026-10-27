from django.urls import path

from . import views

urlpatterns = [
    path("backups/", views.BackupListView.as_view(), name="backups"),
    path("backups/<str:slug>", views.BackupDetailView.as_view(), name="backup"),
]
