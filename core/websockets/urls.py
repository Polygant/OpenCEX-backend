from django.urls.conf import path

from core.websockets.consumers import LiveNotificationsConsumer

urlpatterns = [
    path("live_notifications", LiveNotificationsConsumer.as_asgi()),
]
