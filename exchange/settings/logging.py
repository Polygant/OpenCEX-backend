import logging
import os

from .common import DEBUG


ORDERBOOK_LOG_LEVEL = logging.DEBUG

ENVIRONMENT = 'local'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'static_fields': {
            '()': 'exchange.loggers.StaticFieldFilter',
            'fields': {
                'project': 'exchange',
                'environment': ENVIRONMENT,
            },
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'BitcoinRPC': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
    },
}

if DEBUG:
    # logs
    LOGGING['loggers']['']['level'] = 'DEBUG'
