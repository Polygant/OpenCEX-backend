#!/usr/bin/env python3
import logging
import os
import sys

from celery.apps.worker import Worker

os.putenv('LANG', 'C.UTF-8')
os.putenv('LC_ALL', 'C.UTF-8')
import click
from celery.signals import celeryd_after_setup, worker_process_init,\
    worker_shutdown
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exchange.settings')
sys.path.append(os.path.join(sys.path[0], '..'))

from exchange.celery_app import app
app.autodiscover_tasks(['core'])
from core.models.inouts.pair import Pair
from lib.oneinstlock import MultiLock, AutoLock


class StackPairLock(AutoLock):
    PREFIX = 'stack-pair-lock-'


class StackLock(MultiLock):
    LOCK_CLASS = StackPairLock


@click.command()
@click.option('--debug', is_flag=True)
@click.option('--pairs', default=None, help='pairs to process', type=str)
def cli(debug, pairs):
    app.conf.worker_redirect_stdouts = False

    if pairs:
        pairs = pairs.split(',')

    else:
        pairs = [i.code for i in Pair.objects.all()]

    lock = StackLock(pairs)
    lock.acquire()

    queues = ['orders.{}'.format(i.upper()) for i in pairs]
    pairs_model = [Pair.get(i) for i in pairs]

    options = {
        'app': app,
        'loglevel': 'ERROR',
        'traceback': True,
        'queues': queues,
        'exclude_queues': ['celery'],
        'concurrency': 1,
        'quiet': True,
        'worker_prefetch_multiplier': 100
    }

    logging.info(f'QUEUES to LISTEN: {(" ").join(queues)}')

    @worker_shutdown.connect
    def stop_lock(*args, **kwargs):
        lock.release()

    @celeryd_after_setup.connect
    def setup_direct_queue(sender, instance, **kwargs):
        from core.stack_processor import StackProcessor

        loglevel = logging.DEBUG if debug else logging.INFO
        sp = StackProcessor.get_instance(loglevel, pairs=pairs_model)
        sp.load_opened_orders()
        logging.getLogger('celery').setLevel(loglevel)

    @worker_process_init.connect
    def wrp(sender, *args, **kwargs):
        logging.info('started %s', queues)
        from core.stack_processor import StackProcessor
        sp = StackProcessor.get_instance(pairs=pairs_model)
        sp.start_cache_updaters()

    wrk = Worker(**options)

    wrk.start()


cli()
