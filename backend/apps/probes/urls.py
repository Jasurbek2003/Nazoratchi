from django.urls import path

from . import views

urlpatterns = [
    path("probes/", views.ProbeListView.as_view(), name="probes"),
    path("probes/<uuid:pk>", views.ProbeDetailView.as_view(), name="probe"),
    path("probes/<uuid:pk>/run", views.ProbeRunView.as_view(), name="probe-run"),
    path("probes/<uuid:pk>/results", views.ProbeResultsView.as_view(), name="probe-results"),
    path("probes/<uuid:pk>/uptime", views.ProbeUptimeView.as_view(), name="probe-uptime"),
]
