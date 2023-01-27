import logging
import redis

from django.conf import settings

from django_redis.cache import RedisCache


log = logging.getLogger(__name__)


class PrefixedRedisCache(RedisCache):
    """
    Prefixed cache with init from settings
    """

    @classmethod
    def get_cache(cls, prefix: str) -> RedisCache:
        params = settings.CACHES.get(settings.REDIS_CACHE_NAME, {})
        params['KEY_PREFIX'] = prefix
        location = params.get('LOCATION', '')
        return cls(server=location, params=params)


pool = redis.ConnectionPool(
    host=settings.REDIS['host'],
    port=settings.REDIS['port'],
    db=0,
)

redis_client = redis.Redis(
    connection_pool=pool,
)
