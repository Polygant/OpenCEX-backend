from celery import shared_task

from cryptocoins.data_sources.crypto import binance_data_source, kucoin_data_source
from cryptocoins.data_sources.manager import DataSourcesManager
from lib.utils import memcache_lock


@shared_task
def update_crypto_external_prices():
    """
    Get crypto prices from external exchanges and update cache
    """
    with memcache_lock(f'external_prices_task_lock') as acquired:
        if acquired:
            DataSourcesManager(
                main_source=binance_data_source,
                reserve_source=kucoin_data_source,
            ).update_prices()
