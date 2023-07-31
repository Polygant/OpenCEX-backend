from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from django.urls import path

import core.websockets.urls
from core.auth.hmac_auth import HMACAuthMiddlewareStack


v1 = []
v1.extend(core.websockets.urls.urlpatterns)

urlpatterns = [
    path('wsapi/v1/', URLRouter(v1)),
]

application = ProtocolTypeRouter({
    "websocket": HMACAuthMiddlewareStack(
        URLRouter(urlpatterns),
    ),
})
