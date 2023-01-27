from rest_framework.permissions import AllowAny

from lib.throttling import RedisCacheAnonRateThrottle, RedisCacheUserRateThrottle


class ThrottlingViewMixin:
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )


class NoAuthMixin:
    permission_classes = (AllowAny,)
    authentication_classes = ()
