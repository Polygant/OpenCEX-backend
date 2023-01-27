import json
from datetime import timedelta, datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils.translation import ugettext_lazy as _
from fuzzywuzzy import fuzz
from rest_framework import exceptions

import jwt
from rest_framework_jwt.authentication import JSONWebTokenAuthentication

User = get_user_model()


def our_jwt_payload_handler(user):
    from rest_framework_jwt.utils import jwt_payload_handler
    payload = jwt_payload_handler(user)

    # replace expire token from user settings
    user_timeout = user.profile.auto_logout_timeout
    payload['exp'] = datetime.utcnow() + timedelta(minutes=user_timeout)
    return payload


def get_user_from_token(jwt_value):
    from rest_framework_jwt.settings import api_settings
    jwt_decode_handler = api_settings.JWT_DECODE_HANDLER
    auth = JSONWebTokenAuthentication()

    # TODO error_format
    try:
        payload = jwt_decode_handler(jwt_value)
    except jwt.ExpiredSignature:
        msg = _('Signature has expired.')
        raise exceptions.AuthenticationFailed(msg)
    except jwt.DecodeError:
        msg = _('Error decoding signature.')
        raise exceptions.AuthenticationFailed(msg)
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed()

    user = auth.authenticate_credentials(payload)

    return (user, jwt_value)


class RegisterUserCheck:
    COUNT_LAST_EMAILS = getattr(settings, 'RUC_COUNT_EMAILS', 5)
    MIN_SCORE = getattr(settings, 'RUC_MIN_SCORE', 85)

    cache = cache

    @classmethod
    def get_cache_key(cls):
        return f'ruc:emails'

    @classmethod
    def validate_score_email(cls, email):
        return bool(cls.get_score_email(email) < cls.MIN_SCORE)

    @classmethod
    def get_score_email(cls, email):
        last_emails = cls.get_last_emails()
        max_score = 0
        for last_email in last_emails:
            score = fuzz.token_sort_ratio(email, last_email)
            max_score = max(max_score, score)

        return max_score

    @classmethod
    def update_last_emails(cls) -> str:
        users = User.objects.order_by('-pk')[:cls.COUNT_LAST_EMAILS]
        username_list = list(users.values_list(
            'username',
            flat=True,
        ))
        cache_username_str = json.dumps(username_list)
        cls.cache.set(cls.get_cache_key(), cache_username_str)

        return cache_username_str

    @classmethod
    def get_last_emails(cls):
        cached_str = cache.get(cls.get_cache_key())
        if not cached_str:
            cached_str = cls.update_last_emails()

        cached = json.loads(cached_str)
        return cached
