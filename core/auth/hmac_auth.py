import hashlib
import hmac
import logging

from asgiref.sync import sync_to_async
from channels.auth import AuthMiddlewareStack
from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication
from rest_framework import exceptions

from core.models.facade import Profile
from lib.cache import redis_client as redis_c

log = logging.getLogger(__name__)


class HMACAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key, access_signature, nonce = get_rest_authorization_header(request=request)

        if not api_key or not access_signature or not nonce:
            raise exceptions.AuthenticationFailed('APIKEY, SIGNATURE or NONCE header does not set')

        try:
            user = get_hmac_user(api_key, access_signature, nonce, request.get_full_path())
            if user:
                return user, None
        except exceptions.AuthenticationFailed as auth_exception:
            raise auth_exception
        except Exception as e:
            log.exception(repr(e))
            raise exceptions.AuthenticationFailed('Auth error')


class HMACAuthMiddleware:
    """
    HMAC authorization middleware for Django Channels 2
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        if b'apikey' in headers and b'signature' in headers and b'nonce' in headers:
            apikey = headers[b'apikey'].decode()
            signature = headers[b'signature'].decode()
            nonce = headers[b'nonce'].decode()

            user = await sync_to_async(get_hmac_user)(apikey, signature, nonce, 'ws')
            scope['user'] = user if user else AnonymousUser()

        return await self.inner(scope, receive, send)


def HMACAuthMiddlewareStack(inner):
    return HMACAuthMiddleware(AuthMiddlewareStack(inner))


def get_hmac_user(api_key, access_signature, nonce, salt=''):
    try:
        nonce = int(nonce)
    except ValueError:
        raise exceptions.AuthenticationFailed('NONCE must be type of int')

    redis_key = 'api_nonce_' + api_key + salt
    last_nonce = int(redis_c.get(redis_key) or 0)
    if last_nonce and nonce + 3 <= last_nonce:
        raise exceptions.AuthenticationFailed('Incorrect NONCE header')

    # find profile
    profile = Profile.objects.filter(api_key=api_key).first()
    if not profile:
        raise exceptions.AuthenticationFailed('APIKEY does not exists')

    # gen signature
    secret_key = profile.secret_key.encode('utf-8')
    message = api_key + str(nonce)
    signature = hmac.new(
        secret_key,
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()

    # check signature
    if access_signature.upper() == signature.upper():
        # add nonce to redis
        redis_c.set(redis_key, nonce)
        return profile.user


def get_rest_authorization_header(request):
    """
    Return request's 'Authorization:' header, as a bytestring.
    """
    key = request.META.get('HTTP_APIKEY')
    signature = request.META.get('HTTP_SIGNATURE')
    nonce = request.META.get('HTTP_NONCE')

    return [key, signature, nonce]
