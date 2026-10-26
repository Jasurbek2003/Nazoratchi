from django.urls import path

from . import views

urlpatterns = [
    path("hb/<str:token>", views.beat, name="heartbeat"),
]
