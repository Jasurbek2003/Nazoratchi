from django.urls import path

from . import views

urlpatterns = [
    path("channels/", views.ChannelListView.as_view(), name="channels"),
    path("channels/<uuid:pk>", views.ChannelDetailView.as_view(), name="channel"),
    path("channels/<uuid:pk>/test", views.ChannelTestView.as_view(), name="channel-test"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
]
