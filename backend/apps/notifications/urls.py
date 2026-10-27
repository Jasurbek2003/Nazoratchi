from django.urls import path

from . import views, webhook

urlpatterns = [
    path("channels/", views.ChannelListView.as_view(), name="channels"),
    path("channels/<uuid:pk>", views.ChannelDetailView.as_view(), name="channel"),
    path("channels/<uuid:pk>/test", views.ChannelTestView.as_view(), name="channel-test"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("telegram/webhook/<str:secret>", webhook.webhook, name="telegram-webhook"),
]
