import logging
from typing import Optional

from celery.apps.worker import Worker
from celery.signals import worker_process_init, worker_shutdown
from django.conf import settings
from django.core.management.base import BaseCommand

from cryptocoins.coin_service import CoinServiceBase
from cryptocoins.utils.service import set_service_instance
from exchange.celery_app import app


log = logging.getLogger(__name__)


class BaseWorker(BaseCommand):
    """
    Coin processing worker base class
    """
    SERVICE_CLASS: Optional[CoinServiceBase] = None

    _default_options = {
        'loglevel': 'DEBUG' if settings.DEBUG else 'INFO',
        'traceback': True,
        'exclude_queues': [
            'celery',
        ],
        'concurrency': 1,
    }

    @property
    def service_class(self):
        """
        get service class
        """
        if not self.SERVICE_CLASS:
            raise NotImplementedError
        return self.SERVICE_CLASS

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super().__init__(stdout, stderr, no_color)

        if self.service_class is None:
            raise ValueError('service_class must be set')

        self.queue_name = self.service_class().currency.code.lower()
        self._worker = None

    def handle(self, *args, **options):
        log.info('Starting for queue %s', self.queue_name)

        worker_options = self._get_worker_options({
            'app': app,
            'queues': [
                self.queue_name,
            ],
        })
        log.info('Setting service instance')
        service = self.service_class()
        set_service_instance(service)

        log.info('Setup worker')
        self._worker = Worker(**worker_options)

        # connect signals
        log.info('Connecting signals')
        worker_process_init.connect(self._on_worker_init)
        worker_shutdown.connect(self._on_shutdown)

        log.info('Worker run')
        self._worker.start()

    def _get_worker_options(self, custom_options: dict) -> dict:
        options = self._default_options
        options.update(custom_options)

        return options

    def _on_worker_init(self, *args, **kwargs):
        log.info('Init worker')

    def _on_shutdown(self, *args, **kwargs):
        log.info('Shutting down')
