import logging
import time

from django.conf import settings

from core.consts.orders import BUY
from core.models.orders import EXCHANGE
from core.models.orders import MARKET
from core.models.orders import ORDER_CLOSED
from core.models.orders import ORDER_OPENED
from core.models.orders import Order
from core.models.orders import SELL
from lib.helpers import to_decimal
from .actions import Actions
from .stack import ASC
from .stack import BaseStack
from .stack import DESC
from ..utils.facade import is_bot_user


class OrderProcessor(object):
    def __init__(self, book, order):
        self.book: OrderBook = book
        self.order: Order = order
        if is_bot_user(order.user.username):
            self.stack = self.book.bot_buys if order.operation == SELL else self.book.bot_sells
            self.this_order_stack = self.book.bot_buys if order.operation != SELL else self.book.bot_sells
        else:
            self.stack = self.book.buys if order.operation == SELL else self.book.sells
            self.this_order_stack = self.book.buys if order.operation != SELL else self.book.sells
        self.is_market = order.type in [MARKET, EXCHANGE]
        self.logger = book.logger.getChild('{}_{}'.format(order.operation_str, order.id))

    def price_match(self, price):
        if self.is_market:
            return True

        if self.order.operation == SELL:
            return self.order.price <= price
        else:
            return self.order.price >= price

    def process(self):
        if self.order.state != ORDER_OPENED:
            self.logger.debug('NOT process {}. cause NOT OPENED'.format(self.order))
            return

        if self.order.id in self.stack:
            self.logger.debug('NOT process {}. cause already in stack!'.format(self.order))
            return

        self.logger.debug('process {}'.format(self.order))

        if self.is_market:
            self.logger.debug('Market execute')
            return self.market_execute()

        if not self.stack:  # if first order in stack
            self.logger.debug('Empty stack. add order')
            return self.add_to_book()

        if not self.price_match(self.stack.top_price):
            self.logger.debug('Top price {} not match order price {}'.format(self.stack.top_price, self.order.price))
            return self.add_to_book()

        return self.instant_execute(partial=True)

    def is_in_book(self, order):
        pass

    def instant_execute(self, partial=False):
        fulfill, qty, orders = self.matching_orders()

        #  TODO validate order before create # delete!!!
        if self.is_market:
            self.logger.debug('Can not market instant_execute order. cancel')
            return self.cancel_market()

        self.execute_order_with_matched(orders)

        if self.order.state == ORDER_OPENED:
            self.logger.debug('not executed totally. add {}'.format(self.order))
            return self.add_to_book()

        self.logger.debug('Executed totally! {}'.format(self.order))

    def market_execute(self):
        if self.order.operation == BUY:
            fulfill, qty, orders = self.market_matching_orders()
        else:
            fulfill, qty, orders = self.matching_orders()

        if not fulfill:
            self.logger.debug('Can not fullfil  market order. cancel')
            return self.cancel_market()

        self.execute_order_with_matched(orders)

        if self.order.state == ORDER_OPENED and self.order.type != self.order.ORDER_TYPE_EXCHANGE:
            self.logger.debug('not executed totally. add {}'.format(self.order))
            return self.add_to_book()

        if self.order.cost and self.order.cost > 0:
            self.order.close_market()

        self.logger.debug('Executed totally! {}'.format(self.order))

    def execute_order_with_matched(self, orders):
        from django.core import serializers
        from core.tasks.orders import stop_limit_processor

        for order in orders:
            self.execute_order_with(order)
            data = serializers.serialize('json', [order])
            stop_limit_processor.apply_async([data])
            if order.operation == SELL and (
                    order.quantity_left * order.price) < getattr(settings, 'MIN_COST_ORDER_CANCEL', 0.0000001):
                # order from stack
                self.book.cancel_order(order)

        if self.order.operation == SELL and (
                self.order.quantity_left * self.order.price) < getattr(settings, 'MIN_COST_ORDER_CANCEL', 0.0000001):
            # order from event
            if self.is_market:
                self.cancel_market()
            else:
                self.book.cancel_order(self.order)

        data = serializers.serialize('json', [self.order])
        stop_limit_processor.apply_async([data])

        self.logger.debug('processed updated {}'.format(self.order))

    def execute_order_with(self, order: Order):
        self.logger.debug('matched order {}'.format(order))
        self.order.execute(order)

        if order.state == ORDER_CLOSED:
            self.stack.remove(order)
            self.logger.debug('totaly executeed matched order {}'.format(order))
            self.book.actions.order_processed(order)

        self.logger.debug('matched updated {}'.format(order))

    def cancel_market(self):
        self.logger.debug('Market cancel')
        self.order.cancel_order()

    def cancel(self):
        self.logger.debug('Market cancel')
        self.logger.debug('Cancel {}'.format(self.order))

        self.this_order_stack.remove(self.order)
        self.order.cancel_order()
        self.book.actions.order_cancelled(self.order)

    def matching_orders(self):
        orders = []
        quantity = 0
        fulfill = False

        self.logger.debug(', '.join([str(round(i.price, 4)) for i in self.stack[:5]]))

        for order in self.stack:
            if not self.price_match(order.price):
                self.logger.debug('not ok {}'.format(order.price))
                break

            self.logger.debug('ok {}'.format(order.price))
            orders.append(order)
            quantity = quantity + order.quantity_left

            if quantity >= self.order.quantity_left:
                fulfill = True
                self.logger.debug('FULLFILL!')
                break
        self.logger.debug(', '.join([str(round(i.price, 4)) for i in orders]))
        return fulfill, quantity, orders

    def market_matching_orders(self):

        orders = []
        quantity = 0
        fulfill = False
        order_cost = self.order.cost

        for order in self.stack:
            orders.append(order)
            current_cost = order.quantity_left * order.price
            quantity += order.quantity_left

            order_cost -= current_cost
            if order_cost <= 0:
                fulfill = True
                break

        return fulfill, quantity, orders

    def add_to_book(self):
        self.this_order_stack.add(self.order)


class OrderBook(object):
    STACK_CLASS = BaseStack
    ORDER_PROCESSOR_CLASS = OrderProcessor
    ACTIONS_CLASS = Actions

    def __init__(self, pair, loglevel=logging.DEBUG):
        self.pair: str = pair
        self.sells = self.STACK_CLASS(ASC)  # ask
        self.buys = self.STACK_CLASS(DESC)  # bid
        self.bot_sells = self.STACK_CLASS(ASC)  # ask
        self.bot_buys = self.STACK_CLASS(DESC)  # bid
        self.actions = self.ACTIONS_CLASS(self)
        self.logger = logging.getLogger('book:' + self.pair)
        # self.logger.info('Book init')
        # self.logger.setLevel(loglevel)

    def process_order(self, order):
        processor: OrderProcessor = self.ORDER_PROCESSOR_CLASS(self, order)
        result = processor.process()
        self.actions.order_processed(order)

        return result

    def cancel_order(self, order: Order):
        self.logger.debug('Cancel {}'.format(order))

        processor: OrderProcessor = self.ORDER_PROCESSOR_CLASS(self, order)
        processor.cancel()

    def remove_order_from_stack(self, order):
        stack = self.sells if order.operation == SELL else self.buys
        stack.remove(order)

    def is_exists_in_stack(self, order):
        stack = self.sells if order.operation == SELL else self.buys
        return order.id in stack

    @staticmethod
    def order_to_dict(order):
        return {'id': order.id,
                'price': order.price,
                'quantity': order.quantity_left,
                'user_id': order.user_id,
                'timestamp': order.created.timestamp()
                }

    def get_rate(self):
        values = []
        if self.sells:
            values.append(self.sells.top_price)
        if self.buys:
            values.append(self.buys.top_price)
        if not values:
            return None

        return to_decimal(1.0) * sum(values) / len(values)

    def get_stats(self, stack):
        amounts = [i.quantity_left for i in stack]
        total_volume = sum(amounts)
        prices = [i.price for i in stack]
        if total_volume > 0:
            weighted_avg = sum(x * y for x, y in zip(prices, amounts)) / total_volume
        else:
            weighted_avg = None

        return total_volume, weighted_avg

    def get_stats_buys(self, stack):
        amounts = [i.quantity_left for i in stack]
        total_volume = sum(amounts)
        prices = [i.price for i in stack]
        if total_volume > 0:
            weighted_avg = sum(x * y for x, y in zip(prices, amounts)) / total_volume
        else:
            weighted_avg = None

        if weighted_avg:
            return weighted_avg * total_volume, weighted_avg
        else:
            return total_volume, weighted_avg

    def export(self, limit=100):
        sells_volume, sells_w_avg = self.get_stats(self.sells)
        buys_volume, buys_w_avg = self.get_stats_buys(self.buys)

        return {
            'sells_w_avg': sells_w_avg,
            'buys_w_avg': buys_w_avg,
            'sells_volume': sells_volume,
            'buys_volume': buys_volume,
            'top_sell': self.sells.top_price,
            'top_buy': self.buys.top_price,
            'rate': self.get_rate(),
            'sells': self.export_orders_prepare(self.sells[:limit]),
            'buys': self.export_orders_prepare(self.buys[:limit]),
            'ts': time.time() * 1000,
            'last_proceed': int((self.actions.last_stack_update or 0) * 1000),
            'last_update': int((self.actions.last_cache_update or 0) * 1000),
            'down_multiplier': self.actions.down_multiplier,
            'down_send_time': self.actions.down_send_time,
            'pair': self.pair
        }

    def export_orders_prepare(self, order_list):
        depth = 0
        result = []
        for i in order_list:
            order = self.order_to_dict(i)
            depth += order['quantity']
            order['depth'] = depth
            result.append(order)
        return result


class PreMatch(object):
    def __init__(self, orders):
        self.orders = orders

    def find_cost_and_price(self, quantity, is_cost=False):
        quantityt_left = to_decimal(quantity)
        cost = 0
        for price, qty in self.orders:
            price = to_decimal(price)
            qty = to_decimal(qty)

            qty = min([quantityt_left, qty])
            current_cost = qty * price
            cost += current_cost
            if is_cost:
                quantityt_left -= current_cost
            else:
                quantityt_left -= qty

            if quantityt_left <= 0:
                return cost, price
        return None, None

    def find_qty_and_price(self, quantity):
        quantityt_left = to_decimal(quantity)
        target_quantity = 0
        target_price = 0
        orders = []

        for price, qty in self.orders:
            price = to_decimal(price)
            qty = to_decimal(qty)

            quoted_amount = price * qty
            q = min([quantityt_left, quoted_amount])
            target_quantity += q / price
            target_price = price
            quantityt_left -= q
            orders.append((price, q / price))

            if quantityt_left <= 0:
                return target_quantity, target_price, orders

        return None, None, orders
