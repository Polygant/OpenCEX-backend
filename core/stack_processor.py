import logging

from django.conf import settings
from django.core import serializers as core_serializer
from django.core.cache import cache
from django.db.models import Sum

from lib.helpers import to_decimal
from core.otcupdater import OtcOrdersBulkUpdater
from core.consts.orders import EXTERNAL, STOP_LIMIT, LIMIT
from core.consts.orders import BUY
from core.consts.orders import MARKET
from core.consts.orders import EXCHANGE
from core.consts.orders import ORDER_OPENED
from core.models.orders import Exchange
from core.models.orders import Order
from core.orderbook.book import OrderBook
from core.models.inouts.pair import Pair
from core.serializers.orders import ExchangeResultSerialzier
from core.serializers.orders import OrderSerializer

log = logging.getLogger(__name__)


class StackProcessor:
    _instance = None
    _pair_instance = None
    _place_order_delay: int = getattr(settings, 'PLACE_ORDER_DELAY', 300)

    def __init__(self, loglevel=logging.INFO, pairs=None):
        self.pairs = [i.code.upper() for i in pairs or Pair.objects.all()]
        self.books = {}
        self.loglevel = loglevel
        self.setup_books()
        self.cancelled = {}

    @staticmethod
    def get_order_from_json(order_data):
        order_d = next(core_serializer.deserialize('json', order_data))
        return order_d.object

    def setup_books(self):
        for pair in self.pairs:
            self.books[pair] = OrderBook(pair, loglevel=self.loglevel)

    def load_opened_orders(self):
        for pair_name in self.pairs:
            pair = Pair.get(pair_name)

            orders = Order.objects.filter(
                state=ORDER_OPENED,
                pair=pair,
                quantity_left__gt=0,
                in_stack=True,
            ).order_by(
                'created',
                'id',
            )

            for order in orders:
                self.books[pair_name].process_order(order)

    def place_order(self, order_data):
        # TODO check if exist order -> except
        order: Order = self.get_order_from_json(order_data)
        key = f'place_order-{order.id}'
        if key in cache:
            log.error(f'order[{order.id}] already on place_order; user[{order.user_id}]')
            cache.touch(key, self._place_order_delay)  # update cache time
            return
        cache.set(key, True, self._place_order_delay)

        book = self.get_book_for_order(order)
        book.process_order(order)

    def get_book_for_order(self, order):
        return self._book_by_pair(order.pair)

    def _book_by_pair(self, pair):
        pair_name = self._pair_name_by_id(pair)
        return self.books[pair_name]

    def start_cache_updaters(self):
        for book in self.books.values():
            book.actions.start_updater()

    @staticmethod
    def _pair_name_by_id(pair_id):
        return Pair.get(pair_id).code

    @classmethod
    def get_order_from_data(cls, order_data):
        order_id = order_data['id']
        #  TODO изменить выборку на фильтр только открытых ордеров ???
        order = Order.objects.select_related('user').filter(id=order_id).first()
        return order

    def cancel_order(self, order_data):
        order_id = order_data['id']
        key = f'stackoncancel-{order_id}'
        if key in cache:
            log.info(f'on cancel {order_id}')
            return
        order: Order = self.get_order_from_data(order_data)
        book: OrderBook = self.get_book_for_order(order)
        book.cancel_order(order)
        cache.set(key, True, 60)

    def update_order(self, order_data):
        order = self.get_order_from_data(order_data)
        book = self.get_book_for_order(order)
        exist_in_stack = book.is_exists_in_stack(order)
        book.remove_order_from_stack(order)
        order._update_order(order_data)
        if exist_in_stack:
            book.process_order(order)

    @classmethod
    def get_instance(cls, loglevel=logging.INFO, renew=False, pairs=None):
        if renew or not cls._instance:
            cls._instance = cls(loglevel=loglevel, pairs=pairs)
        return cls._instance

    def stop_limit_order(self, data):
        order = self.create_stop_limit_order(data)
        if not order:
            return {}
        order = OrderSerializer(instance=order).data
        return order

    def create_stop_limit_order(self, data):
        pair = Pair.get(data['pair'])

        order = Order(
            type=data.get('type', STOP_LIMIT),
            operation=data['operation'],
            user_id=data['user_id'],
            pair=pair,
            price=to_decimal(data.get('price', 0)),
            stop=to_decimal(data.get('stop', 0)),
            quantity=to_decimal(data.get('quantity', 0)),
            in_stack=False,
        )

        order.save()
        return order

    def market_order(self, data):
        book, order = self.create_market_order(data)
        if not order:
            return {}
        book.process_order(order)
        order = OrderSerializer(instance=order).data
        return order

    def create_market_order(self, data):
        pair = Pair.get(data['pair'])
        book = self.books[pair.code]

        order = Order(type=data.get('type', MARKET),
                      operation=data['operation'],
                      user_id=data['user_id'],
                      pair=pair,
                      # price=to_decimal(price),
                      )

        if 'quantity' in data:
            order.quantity = to_decimal(data['quantity'])
        else:
            order.quantity = to_decimal('0')

        if 'cost' in data:
            order.cost = to_decimal(data['cost'])

        order.save()
        return book, order

    def exchange_order(self, data):
        pair = data['pair']
        book = self.books[pair.code]
        order_data = {'pair': pair,
                      # 'quantity': data['quantity'],
                      # 'cost': data['quantity'],
                      'type': EXCHANGE,
                      'operation': data['operation'],
                      'user_id': data['user_id'],
                      }

        if data['strict_pair']:
            order_data['operation'] = data['operation']
            order_data['quantity'] = data['quantity']

        else:
            order_data['operation'] = BUY
            order_data['cost'] = data['quantity']

        _, order = self.create_market_order(order_data)
        if not order:
            return {}

        book.process_order(order)

        # is correct?
        order_cost = order.executionresult_set.aggregate(
            total=Sum('transaction__amount'),
        )['total']

        exchange = Exchange(
            user_id=data['user_id'],
            quote_currency=data['quote_currency'],
            base_currency=data['base_currency'],
            quantity=data['quantity'],
            order=order,
            cost=order_cost,
            operation=data['operation']
        )
        exchange.save()
        exchange = ExchangeResultSerialzier(instance=exchange).data
        return exchange

    def otc_bulk_update(self, pair='BTC-USDT'):
        pair = Pair.get(pair)

        orders = list(Order.objects.filter(
            type=EXTERNAL,
            state=ORDER_OPENED,
            pair=pair)
        )

        book = self._book_by_pair(pair)

        updater = OtcOrdersBulkUpdater(orders, pair)
        orders2reload = updater.start()

        book.actions.set_cache_update(False)

        for order in orders2reload:
            book.remove_order_from_stack(order)

        for order in orders2reload:
            book.process_order(order)

        book.actions.set_cache_update(True)
        book.actions.set_cache()
