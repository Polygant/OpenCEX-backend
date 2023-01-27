import datetime

from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from core.currency import Currency
from core.models.inouts.fees_and_limits import FeesAndLimits
from lib.helpers import to_decimal
from lib.notifications import send_telegram_message
from core.consts.orders import SELL

from core.exceptions.orders import OrderMinQuantityError, OrderMaxCostError


class OrderLimitChecker(object):
    @classmethod
    def check(cls, order):
        if not settings.ORDER_LIMIT:
            return

        if order.operation == SELL:
            currency = order.pair.base
            cost = to_decimal(order.quantity)
        else:
            currency = order.pair.quote
            cost = to_decimal(order.quantity) * to_decimal(order.price or 1)

        cls.check_cost(currency, cost, order.pair, order.id)
        cls.check_min_quantity(order)

    @classmethod
    def get_limit(cls, currency_code):
        return FeesAndLimits.get_limit(currency_code, FeesAndLimits.ORDER, FeesAndLimits.MAX_VALUE)

    @classmethod
    def check_cost(cls, currency, cost, pair, order_id=None):
        limit = cls.get_limit(currency.code)
        if limit is None:
            return

        if cost > limit:
            if not cache.get(pair.code, None):
                cache.set(pair.code, 1, 60*60*24)
                order_id = order_id if order_id else "Empty"
                send_telegram_message(
                    f"AUTO order update error: pair: {pair.code}, order ID: {order_id}")
            raise OrderMaxCostError(
                currency=currency,
                limit=limit,
                actual_cost=cost,
            )

    @classmethod
    def check_min_quantity(cls, order):
        min_quantity = get_min_quantity(order.pair.base)
        if order.quantity < min_quantity:
            raise OrderMinQuantityError(
                currency=order.pair.base,
                min_quantity=min_quantity,
            )


def get_min_quantity(currency: Currency) -> Decimal:
    min_quantity = FeesAndLimits.get_limit(
        currency.code, FeesAndLimits.ORDER, FeesAndLimits.MIN_VALUE)

    # here is no limit
    if min_quantity is None:
        return to_decimal(0)

    return to_decimal(min_quantity)
