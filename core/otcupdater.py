import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache

from core.exceptions.pairs import NotSupportedPairs

try:
    # Django 3.1 and above
    from django.utils.functional import classproperty
except ImportError:
    from django.utils.decorators import classproperty

from django.utils.translation import ugettext_lazy as _
from core.cache import cryptocompare_pairs_price_cache
from core.cache import external_exchanges_pairs_price_cache
from core.consts.orders import EXTERNAL
from core.consts.orders import BUY
from core.models import PairSettings
from core.models.inouts.pair import Pair
from lib.helpers import calc_relative_percent_difference
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class OtcOrdersUpdater:
    """ updater that uses stack.order update tasks """
    PRICE_CACHE_KEY = 'otc-binance'
    # SUPPORTED_PAIRS = ('BTC-USDT', 'ETH-USDT')
    BITSTAMP_PAIRS = ()
    BINANCE_PAIRS = ('BTC-USDT', 'ETH-USDT', 'TRX-USDT')

    @classproperty
    def SUPPORTED_PAIRS(self):
        return PairSettings.get_autoorders_enabled_pairs()

    def __init__(self, orders, pair=None):
        if pair is None:
            pair = Pair.get('BTC-USDT')
        else:
            pair = Pair.get(pair)

        if pair.code.upper() not in self.SUPPORTED_PAIRS:
            raise NotSupportedPairs(_(f'Only {self.SUPPORTED_PAIRS} supported.'))

        self.pair = pair
        self.orders = orders

    @classmethod
    def make_price(cls, pair, percent=0):
        pair = Pair.get(pair)

        pair_code = pair.code.upper()
        if pair_code not in cls.SUPPORTED_PAIRS:
            raise NotSupportedPairs(_(f'Only {cls.SUPPORTED_PAIRS} supported.'))

        # percent = 1  =>  share = 1.01
        # percent = -2  =>  share = 0.98
        share = to_decimal(1) + to_decimal(percent) / to_decimal(100)

        price = to_decimal(cls.get_cached_price(pair_code))
        return price * share

    @classmethod
    def get_ticker_url(cls, pair_code='BTC-USDT') -> str:
        if pair_code in cls.BITSTAMP_PAIRS:
            pair_code = pair_code.replace('-', '').lower()
            return f'https://www.bitstamp.net/api/v2/ticker/{pair_code}/'
        else:
            symbol = cls._get_ticker_symbol(pair_code)
        return f'https://api.binance.com/api/v1/trades?symbol={symbol}&limit=1'

    def start(self):
        self.current_price = self.make_price(self.pair, 0)
        return self.process_orders()

    def get_new_order_price(self, percent):
        share = to_decimal(1) + to_decimal(percent) / to_decimal(100)
        return self.current_price * share

    def process_orders(self):
        updated_orders = []
        for order in self.orders:
            order._price_updated = False
            if order.pair != self.pair or order.type != EXTERNAL:
                continue
            new_price = self.get_new_order_price(order.data['otc_percent'])
            limit = order.data['otc_limit']
            if order.operation == BUY:
                new_price = min([new_price, limit])
            else:
                new_price = max([new_price, limit])
            if order.price == new_price:
                continue
            order._price_updated = True
            self.update_order_price(order, new_price)
            updated_orders.append(order)
        return updated_orders

    def update_order_price(self, order, price):
        price = round(price, 5)
        order.update_order({'id': order.id, 'price': price}, nowait=True)

    @classmethod
    def update_cached_price(cls, pair_code):
        """
        Get actual price from API and store into cache.
        Binance API call limit: 90rps

        pair_code format: BTC-USD
        """
        price = cls.get_price(pair_code)
        key_name = f'{cls._get_cache_key(pair_code)}-price'
        cache.set(key_name, price)
        return price

    @classmethod
    def get_price(cls, pair_code):
        ticker_url = cls.get_ticker_url(pair_code)
        ticker_data = cls._api_get_request(ticker_url)
        if pair_code in cls.BITSTAMP_PAIRS:
            price = Decimal(ticker_data['last'])
        else:
            price = Decimal(ticker_data[0]['price'])
        return price  # no default here

    @classmethod
    def get_cached_price(cls, pair_code):
        pair = Pair.get(pair_code)
        price = to_decimal(external_exchanges_pairs_price_cache.get(pair) or 0)
        return price

    @classmethod
    def _api_get_request(cls, url: str, params: dict=None) -> dict:
        if params is None:
            params = {}

        response = requests.get(url, params)
        response.raise_for_status()

        return response.json()

    @staticmethod
    def _get_ticker_symbol(pair_code: str) -> str:
        """
        BTC-USD -> btcusd
        """
        symbol = pair_code.replace('-', '').upper()
        if symbol == 'BTCUSD':
            symbol = 'BTCUSDT'
        return symbol.upper()

    @classmethod
    def _get_cache_key(cls, pair_code: str) -> str:
        prefix = settings.PRICE_UPDATE_CACHES[cls.PRICE_CACHE_KEY]['cache_key_prefix']
        return f'{prefix}-{cls._get_ticker_symbol(pair_code)}'


class OtcOrdersBulkUpdater(OtcOrdersUpdater):
    """ in stack otc order updater
        changes prices right in db.
        all stack stuff done outside of this code
    """

    def process_orders(self):
        updated_orders = []
        for order in self.orders:
            order._otc_price_updated = False
            if order.pair != self.pair or order.type != EXTERNAL:
                continue

            new_price = self.get_new_order_price(order.otc_percent)

            if new_price == 0:
                continue

            if order.operation == BUY:
                new_price = min([new_price, order.otc_limit])
            else:
                new_price = max([new_price, order.otc_limit])

            if order.price == new_price:
                continue

            # check deviation
            cc_price = cryptocompare_pairs_price_cache.get(order.pair)
            if calc_relative_percent_difference(new_price, order.price) > settings.EXTERNAL_PRICES_DEVIATION_PERCENTS:
                if cc_price and calc_relative_percent_difference(new_price, cc_price) > settings.CRYPTOCOMPARE_DEVIATION_PERCENTS:
                    continue

            try:
                order._update_order({'price': new_price, 'is_external': True})
            except Exception as e:
                log.exception('OTCOrderUpdater exception')
                continue

            order._otc_price_updated = True
            updated_orders.append(order)

        return updated_orders
