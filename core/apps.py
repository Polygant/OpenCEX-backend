import logging

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules

from core.consts.settings import DEFAULT_SETTINGS

log = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # noinspection PyUnresolvedReferences
        import core.signal_handlers.facade
        # noinspection PyUnresolvedReferences
        import core.signal_handlers.orders
        # noinspection PyUnresolvedReferences
        import core.signal_handlers.inouts
        # noinspection PyUnresolvedReferences
        import core.signal_handlers.wallet_history

        from core.utils.facade import load_api_callback_urls_cache
        log.debug('Initialize app')
        # load_api_callback_urls_cache()
