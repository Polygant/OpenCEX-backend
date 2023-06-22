import logging

from celery import shared_task

from cryptocoins.data_sources.crypto import binance_data_source, kucoin_data_source
from cryptocoins.data_sources.manager import DataSourcesManager
from lib.utils import memcache_lock

log = logging.getLogger(__name__)

@shared_task
def update_crypto_external_prices():
    """
    Get crypto prices from external exchanges and update cache
    """
    try:
        with memcache_lock(f'external_prices_task_lock') as acquired:
            if acquired:
                DataSourcesManager(
                    main_source=binance_data_source,
                    reserve_source=kucoin_data_source,
                ).update_prices()
    except:
        log.exception("update_crypto_external_prices")
