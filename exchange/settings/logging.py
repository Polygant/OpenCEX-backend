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
        # 'graypy': {
        #     'level': 'DEBUG',
        #     'class': 'graypy.GELFUDPHandler',
        #     'host': 'graylog.plgdev.com',
        #     'port': 12201,
        #     'filters': ['static_fields'],
        # },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        # 'graypy': {
        #     'handlers': ['graypy'],
        #     'level': 'DEBUG',
        #     'propagate': True,
        # },
    },
}

if DEBUG:
    # logs
    LOGGING['loggers']['']['handlers'] = ['console']
