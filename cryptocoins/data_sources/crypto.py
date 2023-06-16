from decimal import Decimal
from typing import Dict

import requests
from binance.client import Client as BinanceClient
from django.conf import settings

from core.cache import cryptocompare_pairs_price_cache
from core.models.inouts.pair import Pair
from cryptocoins.interfaces.datasources import BaseDataSource
from lib.helpers import to_decimal


class BinanceDataSource(BaseDataSource):
    NAME = 'Binance'
    MAX_DEVIATION = settings.EXTERNAL_PRICES_DEVIATION_PERCENTS

    def __init__(self):
        self._data: Dict[Pair, Decimal] = {}

    @property
    def data(self) -> Dict[Pair, Decimal]:
        return self._data

    def get_latest_prices(self) -> Dict[Pair, Decimal]:
        binance_client = BinanceClient()
        binance_pairs_data = {bc['symbol']: bc['price'] for bc in binance_client.get_all_tickers()}
        pairs_prices = {}
        for pair in Pair.objects.all():
            pair_exchange_key = f'{pair.base.code}{pair.quote.code}'
            if pair_exchange_key in binance_pairs_data:
                pairs_prices[pair] = to_decimal(binance_pairs_data[pair_exchange_key])
        self._data = pairs_prices
        return pairs_prices

    def is_pair_exists(self, pair_symbol) -> bool:
        binance_client = BinanceClient()
        binance_pairs = [bc['symbol'] for bc in binance_client.get_all_tickers()]
        base, quote = pair_symbol.split('-')
        return f'{base}{quote}' in binance_pairs



class CryptocompareDataSource(BaseDataSource):
    """
    Uses cached values
    """
    NAME = 'Cryptocompare'
    MAX_DEVIATION = settings.CRYPTOCOMPARE_DEVIATION_PERCENTS

    def __init__(self):
        self._data: Dict[Pair, Decimal] = {}

    @property
    def data(self) -> Dict[Pair, Decimal]:
        return self._data

    def get_latest_prices(self) -> Dict[Pair, Decimal]:
        pairs_prices = {}
        for pair in Pair.objects.all():
            pairs_prices[pair] = cryptocompare_pairs_price_cache.get(pair)
        self._data = pairs_prices
        return pairs_prices


class KuCoinDataSource(BaseDataSource):
    NAME = 'KuCoin'
    MAX_DEVIATION = settings.EXTERNAL_PRICES_DEVIATION_PERCENTS

    def __init__(self):
        self._data: Dict[Pair, Decimal] = {}

    @property
    def data(self) -> Dict[Pair, Decimal]:
        return self._data

    def get_latest_prices(self) -> Dict[Pair, Decimal]:
        data = requests.get('https://api.kucoin.com/api/v1/market/allTickers').json()['data']['ticker']
        kucoin_prices_data = {bc['symbol']: bc['last'] for bc in data}

        pairs_prices = {}
        for pair in Pair.objects.all():
            pair_exchange_key = f'{pair.base.code}-{pair.quote.code}'
            if pair_exchange_key in kucoin_prices_data:
                pairs_prices[pair] = to_decimal(kucoin_prices_data[pair_exchange_key])
        self._data = pairs_prices
        return pairs_prices

    def is_pair_exists(self, pair_symbol) -> bool:
        data = requests.get('https://api.kucoin.com/api/v1/market/allTickers').json()['data']['ticker']
        kucoin_pairs = [bc['symbol'] for bc in data]
        return pair_symbol in kucoin_pairs


binance_data_source = BinanceDataSource()
kucoin_data_source = KuCoinDataSource()
