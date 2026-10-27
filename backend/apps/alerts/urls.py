from django.urls import path

from . import views

urlpatterns = [
    path("alert-rules/", views.RuleListView.as_view(), name="alert-rules"),
    path("alert-rules/<uuid:pk>", views.RuleDetailView.as_view(), name="alert-rule"),
    path("alert-rules/<uuid:pk>/test", views.RuleTestView.as_view(), name="alert-rule-test"),
    path("alerts/", views.AlertListView.as_view(), name="alerts"),
    path("incidents/", views.IncidentListView.as_view(), name="incidents"),
    path("incidents/<uuid:pk>", views.IncidentDetailView.as_view(), name="incident"),
    path("incidents/<uuid:pk>/ack", views.IncidentAckView.as_view(), name="incident-ack"),
    path(
        "incidents/<uuid:pk>/comments",
        views.IncidentCommentView.as_view(),
        name="incident-comments",
    ),
    path(
        "incidents/<uuid:pk>/resolve", views.IncidentResolveView.as_view(), name="incident-resolve"
    ),
    path("silences/", views.SilenceListView.as_view(), name="silences"),
    path("silences/<uuid:pk>", views.SilenceCancelView.as_view(), name="silence"),
    path("maintenance/", views.MaintenanceListView.as_view(), name="maintenance-list"),
    path("maintenance/<uuid:pk>", views.MaintenanceCancelView.as_view(), name="maintenance"),
]
