import functools
import logging
import random
import sys
import time

from django.utils import timezone

from bots.cache import previous_ohlc_period_price_cache
from bots.exceptions import BotExitCondition
from bots.exchanges.binance import BinanceExchange
from bots.exchanges.main_exchange import MainExchange
from bots.helpers import get_ranged_random
from bots.models import BotConfig
from bots.structs import OrderType, OrderSide, OrderStruct
from core.cache import external_exchanges_pairs_price_cache
from cryptocoins.tasks import update_crypto_external_prices
from lib.helpers import pretty_decimal, to_decimal, to_decimal_pretty
from lib.notifications import send_telegram_message

log = logging.getLogger(__name__)


EXTERNAL_PRICE_PERCENT_DIFFERENCE = 3

PRICE_MIN_DELTA = to_decimal(0.0001)

money_format = functools.partial(pretty_decimal, digits=2)
crypto_format = functools.partial(pretty_decimal, digits=8)


class Bot:
    """
    Trading bot implementation
    """
    logged = False

    def __init__(self, bot_config):
        self.bot_config: BotConfig = bot_config
        self.user = self.bot_config.user
        self.pair = self.bot_config.pair
        self.log = log
        self.main_exchange = MainExchange(bot_config, logger=self.log)
        self.binance = BinanceExchange(bot_config, login=False, logger=self.log)

    def run(self):
        """
        Bot logic entrypoint
        """
        # call strategy
        strategy_method_name = self.bot_config.strategy
        strategy_method_name = 'strategy_' + strategy_method_name
        try:
            strategy_method = getattr(self, strategy_method_name)
        except AttributeError:
            self.log.error('No such method: %s', strategy_method_name)
            return

        self.log.info('Running strategy method %s', strategy_method_name)
        start_time = time.time()
        strategy_method()
        self.log.info('Strategy execution time: %s s', f'{(time.time() - start_time):.3f}')

    @staticmethod
    def is_bot_order(order: OrderStruct):
        return order.is_bot

    def get_random_quantity(self):
        return get_ranged_random(
            min=self.bot_config.min_order_quantity,
            max=self.bot_config.max_order_quantity,
        )

    @staticmethod
    def add_fraction(value, fraction):
        return to_decimal(value) + (to_decimal(value) * to_decimal(fraction))

    @staticmethod
    def substract_fraction(value, fraction):
        return to_decimal(value) - (to_decimal(value) * to_decimal(fraction))

    def get_max_limit_nousers(self, sell_orders_qs, min_limit, max_limit):
        for order in sell_orders_qs:
            if order.price <= min_limit:
                return
            if order.price > max_limit:
                return max_limit
            if not self.is_bot_order(order):
                return order.price
        return max_limit

    def get_min_limit_nousers(self, buy_orders_qs, min_limit, max_limit):
        for order in buy_orders_qs:
            if order.price >= max_limit:
                return
            if order.price < min_limit:
                return min_limit
            if not self.is_bot_order(order):
                return order.price
        return min_limit

    def get_external_or_custom_price(self, update_price=True):
        if self.bot_config.use_custom_price:
            self.log.info('%s Use custom order price: %s',
                          self.bot_config.name, self.bot_config.custom_price)
            if not self.bot_config.custom_price:
                self.log.warning('%s Custom price is not set', self.bot_config.name)
                return
            external_pair_price = self.bot_config.custom_price
        else:
            external_pair_price = external_exchanges_pairs_price_cache.get(self.pair)

        if external_pair_price is None:
            if update_price:
                update_crypto_external_prices()
                external_pair_price = self.get_external_or_custom_price(False)
            else:
                raise BotExitCondition('%s External price unavailable', self.bot_config.name)

        return external_pair_price

    def get_external_price_with_min_max(self):
        external_pair_price = self.get_external_or_custom_price()
        delta = self.bot_config.ext_price_delta
        min_price = self.substract_fraction(external_pair_price, delta)
        max_price = self.add_fraction(external_pair_price, delta)
        return external_pair_price, min_price, max_price

    def make_order(self, order: OrderStruct):
        if order.side == OrderSide.SELL:
            order_currency = self.pair.base.code
            amount = order.quantity
        else:
            order_currency = self.pair.quote.code
            amount = order.quantity * order.price
        order_balance = self.main_exchange.free_balance()[order_currency]
        if amount > order_balance:
            self.stop()
            send_telegram_message(
                f"Bot Alert. Unable to create order.\n{order_currency}\nBalance:{order_balance}")
            return
        order = self.main_exchange.make_order(order)
        return order

    def cancel_order(self, order_id):
        self.main_exchange.cancel_order(order_id)

    def cancel_all_orders(self):
        self.main_exchange.cancel_all_orders()

    def check_low_orders_match(self):
        # Works only with mid_spreading and rand_limit
        result = self.bot_config.low_orders_match
        if result:
            self.log.info('Low orders match is enabled')
        return result

    def low_orders_match(self, attempt=1):
        order_book = self.main_exchange.orderbook()

        lowest_sell_order = order_book.lowest_sell
        highest_buy_order = order_book.highest_buy

        self.log.info('Low orders match attempt %s' % attempt)

        # 1) Compare spreads
        current_spread = round(lowest_sell_order.price - highest_buy_order.price, 4)
        self.log.info('Current spread: %s, settings spread: %s' %
                      (current_spread, self.bot_config.low_orders_spread_size))
        if current_spread >= self.bot_config.low_orders_spread_size:
            self.log.info('Current spread is greater. Continue with strategy logic')
            return True

        # 2) Check size
        self.log.info('Checking orders sizes')
        self.log.info('Buy Order: price:%s,size:%s   Sell order: price: %s,size:%s  max_match_size:%s ' %
                      (highest_buy_order.price, highest_buy_order.amount,
                       lowest_sell_order.price, lowest_sell_order.amount,
                       self.bot_config.low_orders_max_match_size))

        if lowest_sell_order.amount > self.bot_config.low_orders_max_match_size and \
                highest_buy_order.amount > self.bot_config.low_orders_max_match_size:
            self.log.info(
                'Both order sizes are greater then max_match_size. Continue with strategy logic')
            if self.bot_config.low_spread_alert:
                msg = '%s - %s - Buy: %s  Sell:%s - Торги остановлены' % \
                      (self.bot_config.name, current_spread, highest_buy_order, lowest_sell_order)
                send_telegram_message(msg, log)
            self.cancel_all_orders()
            return True

        # 3) Make counter order
        if self.bot_config.low_orders_match_greater_order and \
                lowest_sell_order.amount <= self.bot_config.low_orders_max_match_size and \
                highest_buy_order.amount <= self.bot_config.low_orders_max_match_size:

            target_order = lowest_sell_order if \
                lowest_sell_order.amount > highest_buy_order.amount else highest_buy_order
            self.log.info('Match greater order: %s' % target_order)

        else:
            if highest_buy_order.amount < lowest_sell_order.amount:
                self.log.info('Buy Order price is smaller then max_match_size')
                target_order = highest_buy_order
            else:
                self.log.info('Sell Order price is smaller then max_match_size')
                target_order = lowest_sell_order

        volume = max(target_order.amount, self.bot_config.low_orders_min_order_size)

        counter_order = OrderStruct(
            price=to_decimal_pretty(target_order.price, self.main_exchange.base_symbol_precision),
            quantity=to_decimal_pretty(volume, self.main_exchange.quote_symbol_precision),
            side=OrderSide.SELL if target_order == highest_buy_order else OrderSide.BUY,
        )
        order = self.make_order(counter_order)

        time.sleep(2)
        self.cancel_order(order_id=order.id)
        return False

    def exit(self):
        self.log.info("Shutting down. All open orders will be cancelled.")
        try:
            self.main_exchange.cancel_all_orders()
        except Exception as e:
            self.log.exception("Unable to cancel orders: %s" % e)
        # cache.set(CACHED_BOT_ORDERS_KEYS + self.settings.name, self.orders, timeout=None)
        # cache.delete(ACTIVE_BOTS_CACHE_PREFIX + self.settings.name)
        sys.exit()

    def stop(self):
        self.log.info("Stopping bot...")
        self.bot_config.stopped = True
        self.bot_config.enabled = False
        self.bot_config.save()
        self.exit()

    def strategy_trade_draw_graph(self):
        try:
            if self.check_low_orders_match():
                for i in range(1, 4):
                    if self.low_orders_match(i):
                        self.trade_draw_graph()
                        break
            else:
                self.trade_draw_graph()
        except Exception as e:
            self.log.exception(f'Bot Exception: {e}')
        finally:
            time.sleep(2)
            self.cancel_all_orders()

    def trade_draw_graph(self):
        """
        Simple graph draw strategy
        """
        external_pair_price, min_ext_price, max_ext_price = self.get_external_price_with_min_max()

        self.log.info('%s Min-max %s ext price: %s..%s..%s',
                      self.bot_config.name,
                      self.bot_config.pair,
                      money_format(min_ext_price),
                      money_format(external_pair_price),
                      money_format(max_ext_price))

        open_buy_orders, open_sell_orders = self.main_exchange.get_orders_stack()

        self.log.debug(f'{self.bot_config.name} Sell orders count: {len(open_sell_orders)}, '
                       f'Buy orders count: {len(open_buy_orders)}')

        # main logic
        # check for instant match
        if self.bot_config.instant_match:

            max_price_limit = self.get_max_limit_nousers(
                open_sell_orders, min_ext_price, max_ext_price)
            min_price_limit = self.get_min_limit_nousers(
                open_buy_orders, min_ext_price, max_ext_price)

            if not max_price_limit or not min_price_limit:
                msg = f'Bot {self.bot_config.name} error:\nCan\'t set instant order' \
                      f'\nMax price limit: {max_price_limit}\nMin price limit: {min_price_limit}'
                if self.bot_config.create_order_error:
                    send_telegram_message(msg)
                raise BotExitCondition(msg)

            mid_price = get_ranged_random(min_price_limit, max_price_limit)
            to_cache_price = mid_price

            now = timezone.now()
            begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
            minutes_passed = int((now - begin).total_seconds() / 60)
            is_needed_period = minutes_passed % self.bot_config.ohlc_period == 0

            if is_needed_period and not self.bot_config.is_ohlc_price_used:
                cached_ohlc_price = previous_ohlc_period_price_cache.get(self.bot_config.name)
                if cached_ohlc_price:
                    self.log.info('Using previous OHLC order price')
                    mid_price = cached_ohlc_price
                self.bot_config.is_ohlc_price_used = True
                self.bot_config.save()
            if not is_needed_period:
                self.bot_config.is_ohlc_price_used = False
                self.bot_config.save()

            previous_ohlc_period_price_cache.set(self.bot_config.name, to_cache_price)

            self.log.info('%s Instant order %s min-mid-max: %s..%s..%s',
                          self.bot_config.name,
                          self.bot_config.pair,
                          money_format(min_price_limit),
                          money_format(max_price_limit),
                          money_format(mid_price))

            quantity = self.get_random_quantity()

            buy_order = OrderStruct(
                price=mid_price,
                quantity=quantity,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT
            )
            sell_order = buy_order.copy(side=OrderSide.SELL)

            if random.randint(0, 1):
                # sell
                self.make_order(sell_order)
                # buy
                self.make_order(buy_order)
            else:
                # buy
                self.make_order(buy_order)
                # sell
                self.make_order(sell_order)

            return

        lowest_sell_order = open_sell_orders[0] if open_sell_orders else None
        highest_buy_order = open_buy_orders[0] if open_buy_orders else None

        self.log.info('%s Min-max %s order range: %s..%s',
                      self.bot_config.name,
                      self.bot_config.pair,
                      money_format(highest_buy_order.price if highest_buy_order else 0),
                      money_format(lowest_sell_order.price if lowest_sell_order else 0))

        self.log.info('%s Processing sell', self.bot_config.name)
        if lowest_sell_order is not None:
            self.log.info('%s Lowest sell order exists', self.bot_config.name)
            try:
                # User's order
                if not self.is_bot_order(lowest_sell_order):
                    self.log.info('%s Lowest sell is user made', self.bot_config.name)
                    quantity = self.get_random_quantity()

                    # can match user?
                    if self.bot_config.match_user_orders:
                        # can buy in ext minmax range?
                        if lowest_sell_order.price < max_ext_price:
                            self.log.info('%s Make counter sell user order: %s %s',
                                          self.bot_config.name,
                                          money_format(lowest_sell_order.price),
                                          crypto_format(quantity))

                            self.make_order(OrderStruct(
                                side=OrderSide.BUY,
                                order_type=OrderType.LIMIT,
                                quantity=quantity,
                                price=lowest_sell_order.price,
                            ))
                            raise BotExitCondition(
                                f'{self.bot_config.name} User counter sell order made')

                    price = get_ranged_random(
                        min=external_pair_price,
                        max=max_ext_price,
                    )

                    if highest_buy_order and highest_buy_order.price > price:
                        self.log.info('%s Max buy price: %s, calculated sell price: %s',
                                      self.bot_config.name,
                                      money_format(highest_buy_order.price),
                                      money_format(price))
                        raise BotExitCondition(
                            f'{self.bot_config.name} Sell price greater than max buy price, skipping')

                    if price > lowest_sell_order.price:
                        raise BotExitCondition(
                            f'{self.bot_config.name} Sell price is over user order')

                    self.log.info('%s Make under sell order: %s %s',
                                  self.bot_config.name,
                                  money_format(price),
                                  crypto_format(quantity))

                    self.make_order(OrderStruct(
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=price,
                    ))
                # Bot's order
                else:
                    self.log.info('%s Lowest sell is bot made', self.bot_config.name)
                    price = lowest_sell_order.price
                    if price > max_ext_price:
                        if lowest_sell_order.user == self.user:
                            self.cancel_order(order_id=lowest_sell_order.id)
                            raise BotExitCondition(
                                f'{self.bot_config.name} Sell price greater than max ext price, cancel')

                    if highest_buy_order and highest_buy_order.price > price:
                        raise BotExitCondition(
                            f'{self.bot_config.name} Sell price greater than max buy')

                    # check quantity
                    quantity = lowest_sell_order.quantity_left
                    if quantity < self.bot_config.min_order_quantity:
                        if lowest_sell_order.user == self.user:
                            self.cancel_order(order_id=lowest_sell_order.id)
                            raise BotExitCondition(
                                f'{self.bot_config.name} Cancel sell order less than min quantity')
                    if quantity > self.bot_config.max_order_quantity:
                        quantity = self.get_random_quantity()

                    self.log.info('%s Make counter-sell order: %s %s',
                                  self.bot_config.name,
                                  money_format(price),
                                  crypto_format(quantity))

                    self.make_order(OrderStruct(
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=price,
                    ))

            except BotExitCondition as ex:
                self.log.info('%s Continue after exit condition: %s', self.bot_config.name, str(ex))

        # if no sell orders exists
        else:
            self.log.info('%s Lowest sell order does not exists', self.bot_config.name)
            try:
                quantity = self.get_random_quantity()
                price = get_ranged_random(
                    min=external_pair_price,
                    max=max_ext_price,
                )

                if highest_buy_order and highest_buy_order.price > price:
                    raise BotExitCondition(
                        f'{self.bot_config.name} Sell price greater than max buy price, sipping')

                self.log.info('%s Make new sell order: %s %s',
                              self.bot_config.name,
                              money_format(price),
                              crypto_format(quantity))

                self.make_order(OrderStruct(
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    price=price,
                ))

            except BotExitCondition as ex:
                self.log.info('%s Continue after exit condition: %s', self.bot_config.name, str(ex))

        self.log.info('%s Processing buy', self.bot_config.name)
        if highest_buy_order:
            self.log.info('%s Highest buy order exists', self.bot_config.name)
            try:
                # User's order
                if not self.is_bot_order(highest_buy_order):
                    self.log.info('%s Highest buy is user made', self.bot_config.name)
                    quantity = self.get_random_quantity()

                    # can match user?
                    if self.bot_config.match_user_orders:
                        # can sell in ext minmax range?
                        if highest_buy_order.price > min_ext_price:
                            self.log.info('%s Make counter buy user order: %s %s',
                                          self.bot_config.name,
                                          money_format(highest_buy_order.price),
                                          crypto_format(quantity))

                            self.make_order(OrderStruct(
                                side=OrderSide.SELL,
                                order_type=OrderType.LIMIT,
                                quantity=quantity,
                                price=highest_buy_order.price,
                            ))
                            raise BotExitCondition(
                                f'{self.bot_config.name} Counter-buy user order made')

                    price = get_ranged_random(
                        min=min_ext_price,
                        max=external_pair_price,
                    )

                    if lowest_sell_order and lowest_sell_order.price < price:
                        self.log.info('%s Min sell price: %s, calculated buy price: %s',
                                      self.bot_config.name,
                                      money_format(lowest_sell_order.price),
                                      money_format(price))
                        raise BotExitCondition(
                            f'{self.bot_config.name} Buy price less than min sell price, skipping')

                    if price < highest_buy_order.price:
                        raise BotExitCondition(
                            f'{self.bot_config.name} Sell price is over user order')

                    self.log.info('%s Make over buy order: %s %s',
                                  self.bot_config.name,
                                  money_format(price),
                                  crypto_format(quantity))

                    self.make_order(OrderStruct(
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=price,
                    ))

                # Bot order
                else:
                    self.log.info('%s Highest buy is bot made', self.bot_config.name)
                    price = highest_buy_order.price

                    if price < min_ext_price:
                        if highest_buy_order.user == self.user:
                            self.cancel_order(order_id=highest_buy_order.id)
                            raise BotExitCondition(
                                f'{self.bot_config.name} Buy price greater than min ext price, cancel')

                    if lowest_sell_order and lowest_sell_order.price < price:
                        raise BotExitCondition(
                            f'{self.bot_config.name} Buy price less than min sell')

                    # check quantity
                    quantity = highest_buy_order.quantity_left
                    if quantity < self.bot_config.min_order_quantity:
                        if highest_buy_order.user == self.user:
                            self.cancel_order(order_id=highest_buy_order.id)
                            raise BotExitCondition(
                                f'{self.bot_config.name} Cancel buy order less than min quantity')
                    if quantity > self.bot_config.max_order_quantity:
                        quantity = self.get_random_quantity()

                    self.log.info('%s Make counter-buy order: %s %s',
                                  self.bot_config.name,
                                  money_format(price),
                                  crypto_format(quantity))

                    self.make_order(OrderStruct(
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=price,
                    ))

            except BotExitCondition as ex:
                self.log.info('%s Continue after exit condition: %s', self.bot_config.name, str(ex))

        # if no buy orders exists
        else:
            self.log.info('%s Highest buy order does not exists', self.bot_config.name)
            try:
                quantity = self.get_random_quantity()
                price = get_ranged_random(
                    min=min_ext_price,
                    max=external_pair_price,
                )

                if lowest_sell_order and lowest_sell_order.price < price:
                    raise BotExitCondition(
                        f'{self.bot_config.name} Buy price greater than min sell price, skipping')

                self.log.info('%s Make new buy order: %s %s',
                              self.bot_config.name,
                              money_format(price),
                              crypto_format(quantity))

                self.make_order(OrderStruct(
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    price=price,
                ))

            except BotExitCondition as ex:
                self.log.info('%s Continue after exit condition: %s', self.bot_config.name, str(ex))
