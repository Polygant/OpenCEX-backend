from celery import shared_task

from cryptocoins.data_sources.crypto import binance_data_source, kucoin_data_source
from cryptocoins.data_sources.manager import DataSourcesManager


@shared_task
def update_crypto_external_prices():
    """
    Get crypto prices from external exchanges and update cache
    """

    DataSourcesManager(
        main_source=binance_data_source,
        reserve_source=kucoin_data_source,
    ).update_prices()
