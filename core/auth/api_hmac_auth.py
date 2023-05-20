import hashlib
import hmac
import logging
from typing import Optional, Tuple

from rest_framework import authentication
from rest_framework import exceptions
from django.contrib.auth.models import User

from core.models.facade import Profile
from lib.cache import redis_client as redis_c

log = logging.getLogger(__name__)


class HMACAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key, access_signature, nonce = get_authorization_header(
            request=request)
        return self.authenticate_values(
            api_key, access_signature, nonce
        )

    @staticmethod
    def authenticate_values(
            api_key: Optional[str],
            access_signature: Optional[str],
            nonce: Optional[str]
    ) -> Tuple[User, Optional[str]]:
        if not api_key or not access_signature or not nonce:
            raise exceptions.AuthenticationFailed('APIKEY, SIGNATURE or NONCE header does not set')

        try:
            nonce = int(nonce)
        except ValueError:
            raise exceptions.AuthenticationFailed('NONCE must be type of int')

        try:
            # check nonce by api_key in redis
            redis_key = 'api_nonce_' + api_key
            last_nonce = int(redis_c.get(redis_key) or 0)


            if last_nonce and nonce <= last_nonce:
                raise exceptions.AuthenticationFailed('Incorrect NONCE header')

            # find profile
            profile = Profile.objects.filter(api_key=api_key)
            if len(profile) == 0:
                raise exceptions.AuthenticationFailed('APIKEY does not exists')
            profile = profile[0]

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
                return profile.user, None
            raise exceptions.AuthenticationFailed('Incorrect SIGNATURE header')

        except exceptions.AuthenticationFailed as auth_exception:
            raise auth_exception
        except Exception as e:
            log.exception(repr(e))
            raise exceptions.AuthenticationFailed('Auth error')


def get_authorization_header(request):
    """
    Return request's 'Authorization:' header, as a bytestring.
    """
    key = request.META.get('HTTP_APIKEY')
    signature = request.META.get('HTTP_SIGNATURE')
    nonce = request.META.get('HTTP_NONCE')

    return [key, signature, nonce]
