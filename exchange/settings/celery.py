import os

from celery.schedules import crontab
from exchange.settings import env


# Celery
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'
CELERY_ACCEPT_CONTENT = [
    'json',
    'pickle',
]
os.environ.setdefault('C_FORCE_ROOT', 'true')

# tasks and queues config
DEFAULT_CRYPTO_PAYOUTS_PERIOD = crontab(minute='*')
DEFAULT_CRYPTO_ACCUMULATE_PERIOD = crontab(minute='*')
DEFAULT_CRYPTO_PROCESS_NEW_BLOCKS_PERIOD = crontab(minute='*')

CRYPTO_AUTO_SCHEDULE_CONF = [
    {
        'currency': 'BTC',
        'enabled': True,
        'payouts_period': False,
        'accumulate_period': DEFAULT_CRYPTO_ACCUMULATE_PERIOD,
        'process_new_blocks_period': DEFAULT_CRYPTO_PROCESS_NEW_BLOCKS_PERIOD,
    },

]

AMQP_USER = env('AMQP_USER', default='guest')
AMQP_PASS = env('AMQP_PASS', default='guest')
AMQP_HOST = env('AMQP_HOST', default='localhost')
AMQP_PORT = env('AMQP_PORT', default='5672')

BROKER_URL = f"amqp://{AMQP_USER}:{AMQP_PASS}@{AMQP_HOST}:{AMQP_PORT}//"
