"""
 from https://gist.github.com/rluts/22e05ed8f53f97bdd02eafdf38f3d60a
"""
import base64

from channels.auth import AuthMiddlewareStack
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token


class TokenAuthMiddleware:
    """
    Token authorization middleware for Django Channels 2
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        if b'authorization' in headers:
            try:
                token_name, token_key = headers[b'authorization'].decode().split()

                if token_name == 'Basic':
                    token_key = base64.b64decode(token_key).split(':')[0]

                if token_name in ['Token', 'Basic']:
                    token = Token.objects.get(key=token_key)
                    scope['user'] = token.user

            except Token.DoesNotExist:
                scope['user'] = AnonymousUser()
        return await self.inner(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))
