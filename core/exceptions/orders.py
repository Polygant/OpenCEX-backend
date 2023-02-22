from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import APIException

from lib.exceptions import BaseError
from lib.helpers import pretty_decimal


class OrderNotOpened(APIException):
    status_code = 400
    default_detail = 'OrderNotOpened'
    default_code = 'OrderNotOpened'


class CanNotCancelMarketOrder(APIException):
    status_code = 400
    default_detail = 'CanNotCancelMarketOrder'
    default_code = 'CanNotCancelMarketOrder'


class CanNotUpdateOrder(APIException):
    status_code = 400
    default_detail = 'CanNotUpdateOrder'
    default_code = 'CanNotUpdateOrder'


class OrderMaxCostError(BaseError):
    default_detail = _('Max order size is {limit} {currency}, current size: {actual_cost} {currency}.')
    default_code = 'order_max_cost'

    def __init__(self, currency, limit, actual_cost, detail=None):
        if detail is None:
            digit_places = 8
            if currency.code == 'USDT':
                digit_places = 2

            detail = force_text(self.default_detail).format(
                currency=currency,
                limit=limit,
                actual_cost=pretty_decimal(actual_cost, digits=digit_places),
            )
        super().__init__(detail)


class OrderMinQuantityError(BaseError):
    default_detail = _('Minimal quantity: {min_quantity} {currency}.')
    default_code = 'order_min_qty'

    def __init__(self, currency, min_quantity, detail=None):
        if detail is None:
            detail = force_text(self.default_detail).format(
                currency=currency,
                min_quantity=min_quantity,
            )
        super().__init__(detail)


class OrderPriceInvalidError(BaseError):
    default_detail = _('Invalid price.')
    default_code = 'order_price_invalid'


class OrderStopPriceInvalidError(BaseError):
    default_detail = _('Invalid stop price.')
    default_code = 'order_stop_price_invalid'


class OrderStopInvalidError(BaseError):
    default_detail = _('Invalid stop.')
    default_code = 'order_stop_price_invalid'


class OrderQuantityInvalidError(BaseError):
    default_detail = _('Invalid quantity.')
    default_code = 'order_qty_invalid'


class OrderNotFoundError(BaseError):
    default_detail = _('Order not found.')
    default_code = 'order_not_found'


class OrderNotOpenedError(BaseError):
    default_detail = _('Order executed or cancelled.')
    default_code = 'order_not_opened'

    def __init__(self, order=None):
        detail = self.default_detail

        if order is not None and order.state == order.STATE_CLOSED:
            detail = _('Order closed.')

        elif order is not None and order.state == order.STATE_CANCELLED:
            detail = _('Order cancelled.')

        super().__init__(detail)


class OrderUnknownTypeError(BaseError):
    default_detail = _('Order type unknown.')
    default_code = 'order_type_invalid'


class PriceDeviationError(BaseError):
    default_detail = _('Price deviation too much')
    default_code = 'price_deviation'

    def __init__(self, pair=None, deviation=None):
        detail = self.default_detail

        if pair and deviation:
            detail = _(f'Max deviation for pair {pair} is {deviation:.2f}%')

        super().__init__(detail)

