from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from lib.cache import PrefixedRedisCache

app_cache = PrefixedRedisCache.get_cache(prefix='public-api-app-cache-')
phone_verification_cache = PrefixedRedisCache.get_cache(prefix='phone-verification-cache-')


class RedisCacheAnonRateThrottle(AnonRateThrottle):
    cache = app_cache


class RedisCacheUserRateThrottle(UserRateThrottle):
    cache = app_cache


class PhoneVerificationThrottle(UserRateThrottle):
    cache = phone_verification_cache

    def parse_rate(self, rate):
        return 1, 180  # 1 req per 3 min

