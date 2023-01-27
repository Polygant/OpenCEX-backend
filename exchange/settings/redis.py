from exchange.settings import env

REDIS = {
    'host': env('REDIS_HOST', default='localhost'),
    'port': env('REDIS_PORT', default=6379),
    'pwd': env('REDIS_PASS', default=''),
}

REDIS_CACHE_NAME = 'redis'

CACHES = {
    'default': {
        'BACKEND': 'lib.cache.PrefixedRedisCache',
        'LOCATION': 'redis://' + REDIS['host'] + ':' + str(REDIS['port']) + '/1',
        'OPTIONS': {
            'PASSWORD': REDIS['pwd'],
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
    REDIS_CACHE_NAME: {
        'BACKEND': 'lib.cache.PrefixedRedisCache',
        'LOCATION': 'redis://' + REDIS['host'] + ':' + str(REDIS['port']) + '/1',
        'OPTIONS': {
            'PASSWORD': REDIS['pwd'],
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                (f"redis://:{REDIS['pwd']}@{REDIS['host']}:{REDIS['port']}/1",)
                if REDIS['pwd'] else
                (REDIS['host'], REDIS['port'])
            ],
        },
    }
}