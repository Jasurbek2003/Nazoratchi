from django.urls import path

from . import drills, views

urlpatterns = [
    path("backups/", views.BackupListView.as_view(), name="backups"),
    path("backups/drills", drills.DrillListView.as_view(), name="drills"),
    path("backups/drills/<uuid:pk>", drills.DrillDetailView.as_view(), name="drill"),
    path("backups/<str:slug>", views.BackupDetailView.as_view(), name="backup"),
]
