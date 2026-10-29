from django.urls import path

from . import projects, server_actions, views

urlpatterns = [
    path("servers/", views.ServerListView.as_view(), name="servers"),
    path("servers/<uuid:pk>", views.ServerDetailView.as_view(), name="server"),
    path("servers/<uuid:pk>/pause", server_actions.ServerPauseView.as_view(), name="server-pause"),
    path(
        "servers/<uuid:pk>/resume", server_actions.ServerResumeView.as_view(), name="server-resume"
    ),
    path(
        "servers/<uuid:pk>/archive",
        server_actions.ServerArchiveView.as_view(),
        name="server-archive",
    ),
    path(
        "servers/<uuid:pk>/events", server_actions.ServerEventsView.as_view(), name="server-events"
    ),
    path(
        "servers/<uuid:pk>/agent-update",
        server_actions.ServerAgentUpdateView.as_view(),
        name="server-agent-update",
    ),
    path(
        "servers/<uuid:pk>/tokens", server_actions.ServerTokensView.as_view(), name="server-tokens"
    ),
    path(
        "servers/<uuid:pk>/tokens/<int:token_id>",
        server_actions.ServerTokenDetailView.as_view(),
        name="server-token",
    ),
    path(
        "servers/<uuid:pk>/enroll-token",
        views.ServerEnrollTokenView.as_view(),
        name="server-enroll-token",
    ),
    path("projects/", projects.ProjectListView.as_view(), name="projects"),
    path("projects/ports/next", projects.NextPortsView.as_view(), name="projects-ports-next"),
    path("projects/<uuid:pk>", projects.ProjectDetailView.as_view(), name="project"),
    path(
        "projects/<uuid:pk>/archive", projects.ProjectArchiveView.as_view(), name="project-archive"
    ),
    path(
        "projects/<uuid:pk>/servers", projects.ProjectServersView.as_view(), name="project-servers"
    ),
    path("domains/", projects.DomainListView.as_view(), name="domains"),
    path("domains/<uuid:pk>", projects.DomainDetailView.as_view(), name="domain"),
]
