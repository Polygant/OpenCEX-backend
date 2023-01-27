import logging
from typing import List

from django.core.cache import cache

from bots.helpers import BaseHttpSession
from bots.models import BotConfig
from bots.structs import OrderBookEntryStruct
from bots.structs import OrderStruct

ORDERS_IDS_KEY_PREFIX='bots-app-cache-ids-'


class BaseExchange:
    NAME = 'Base Exchange'
    BASE_URL = ''

    def __init__(self, config: BotConfig, login=True, logger=None):
        self.base_symbol_precision = config.symbol_precision
        self.quote_symbol_precision = config.quote_precision
        self.session = BaseHttpSession(self.BASE_URL)
        self.config = config
        self.orders_ids = self.get_cached_orders()
        self.log = logger or logging.getLogger(__name__)
        self.log.info(f'Starting {self.NAME} exchange')
        if login:
            self.login()

    def add_order_to_cache(self, order_id):
        self.orders_ids.append(order_id)
        cache.set(ORDERS_IDS_KEY_PREFIX + self.config.name, self.orders_ids, timeout=None)

    def remove_order_from_cache(self, order_id):
        if order_id in self.orders_ids:
            self.orders_ids.remove(order_id)
        cache.set(ORDERS_IDS_KEY_PREFIX + self.config.name, self.orders_ids, timeout=None)

    def cancel_all_orders(self):
        self.log.info(f'Cancelling all orders: {self.orders_ids}')
        for order in self.opened_orders():
            self.cancel_order(order.id)
        cache.set(ORDERS_IDS_KEY_PREFIX + self.config.name, [], timeout=None)

    def get_cached_orders(self):
        return cache.get(ORDERS_IDS_KEY_PREFIX + self.config.name, []) or []

    def get_pair(self):
        raise NotImplementedError

    def login(self):
        raise NotImplementedError

    def make_order(self, order: OrderStruct) -> OrderStruct:
        raise NotImplementedError

    def cancel_order(self, order_id) -> None:
        raise NotImplementedError

    def balance(self) -> dict:
        raise NotImplementedError

    def opened_orders(self) -> List[OrderStruct]:
        raise NotImplementedError

    def price(self) -> float:
        raise NotImplementedError

    def orderbook(self) -> OrderBookEntryStruct:
        raise NotImplementedError
