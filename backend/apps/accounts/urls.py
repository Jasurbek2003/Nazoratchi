from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/logout-all", views.LogoutAllView.as_view(), name="auth-logout-all"),
    path("auth/me", views.MeView.as_view(), name="auth-me"),
    path("auth/sessions", views.SessionsView.as_view(), name="auth-sessions"),
    path("auth/sessions/<uuid:public_id>", views.SessionDetailView.as_view(), name="auth-session"),
]
