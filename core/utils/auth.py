import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from fuzzywuzzy import fuzz

from rest_framework_simplejwt.authentication import JWTAuthentication

User = get_user_model()


def get_user_from_token(jwt_value):
    auth = JWTAuthentication()
    payload = auth.get_validated_token(jwt_value)
    user = auth.get_user(payload)
    return user, payload


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
