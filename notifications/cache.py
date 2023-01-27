import redis

from django.conf import settings


NOTIFICATIONS_DB = 4

pool = redis.ConnectionPool(
    host=settings.REDIS['host'],
    port=settings.REDIS['port'],
    db=NOTIFICATIONS_DB,
)

redis_client = redis.Redis(
    connection_pool=pool,
)
