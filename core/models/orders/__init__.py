import logging
from decimal import Decimal

from django.conf import settings
from django.core import serializers as core_serializer
from django.core.cache import cache
from django.db import models
from django.db import transaction
from django.db.models import Case, Q
from django.db.models import F
from django.db.models import Sum
from django.db.models import When
from django.db.transaction import atomic
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.balance_manager import BalanceManager
from core.cache import last_pair_price_cache, external_exchanges_pairs_price_cache
from core.consts.inouts import DISABLE_EXCHANGE
from core.consts.inouts import DISABLE_STACK
from core.consts.orders import EXTERNAL, ORDER_REVERT, STOP_LIMIT
from core.consts.orders import BUY
from core.consts.orders import EXCHANGE
from core.consts.orders import LIMIT
from core.consts.orders import MARKET
from core.consts.orders import OPERATIONS
from core.consts.orders import ORDER_CANCELED
from core.consts.orders import ORDER_CLOSED
from core.consts.orders import ORDER_OPENED
from core.consts.orders import ORDER_STATES
from core.consts.orders import ORDER_TYPES
from core.consts.orders import SELL
from core.currency import CurrencyModelField
from core.exceptions.inouts import NotEnoughFunds
from core.exceptions.orders import CanNotCancelMarketOrder, OrderPriceInvalidError, OrderQuantityInvalidError, \
    OrderNotOpenedError, OrderUnknownTypeError, PriceDeviationError
from core.exceptions.pairs import CoinOrPairsDisable
from core.models import PairSettings
from core.models.facade import Profile
from core.models.inouts.transaction import REASON_ORDER_CACHEBACK, REASON_ORDER_REVERT_RETURN, \
    REASON_ORDER_REVERT_CHARGE
from core.models.inouts.transaction import REASON_ORDER_CANCELED
from core.models.inouts.transaction import REASON_ORDER_CHARGE_RETURN
from core.models.inouts.transaction import REASON_ORDER_EXECUTED
from core.models.inouts.transaction import REASON_ORDER_EXTRA_CHARGE
from core.models.inouts.transaction import REASON_ORDER_OPENED
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.transaction import Transaction
from core.models.inouts.pair import Pair, PairModelField
from core.signals.orders import order_changed
from core.utils.inouts import is_coin_disabled
from core.utils.limits import OrderLimitChecker
from core.utils.limits import get_min_quantity
from core.utils.stats.daily import get_pair_last_price
from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.helpers import to_decimal, copy_instance, calc_relative_percent_difference

LIMIT = LIMIT  # import
# needs to prevent zero fee
MIN_FEE_AMOUNT = to_decimal('0.00000001')

log = logging.getLogger(__name__)


class Order(UserMixinModel, BaseModel):
    # operations
    OPERATION_BUY = BUY
    OPERATION_SELL = SELL

    OPERATIONS = (
        (OPERATION_BUY, _('Buy')),
        (OPERATION_SELL, _('Sell')),
    )

    # order states
    STATE_OPENED = ORDER_OPENED
    STATE_CLOSED = ORDER_CLOSED
    STATE_CANCELLED = ORDER_CANCELED
    STATE_REVERT = ORDER_REVERT

    STATES = (
        (STATE_OPENED, 'Opened'),
        (STATE_CLOSED, 'Closed'),
        (STATE_CANCELLED, 'Cancelled'),
        (STATE_REVERT, 'Moderated'),
    )

    # order types
    ORDER_TYPE_LIMIT = LIMIT
    ORDER_TYPE_MARKET = MARKET
    ORDER_TYPE_EXTERNAL = EXTERNAL
    ORDER_TYPE_EXCHANGE = EXCHANGE
    ORDER_TYPE_STOP_LIMIT = STOP_LIMIT

    ORDER_TYPES = (
        (ORDER_TYPE_LIMIT, _('Limit')),
        (ORDER_TYPE_MARKET, _('Market')),
        (ORDER_TYPE_EXTERNAL, _('External')),
        (ORDER_TYPE_EXCHANGE, _('Exchange')),
        (ORDER_TYPE_STOP_LIMIT, _('Stop limit')),
    )

    STATUS_NOT_SET = 0
    STATUS_REVERTED = 99

    STATUS_LIST = (
        (STATUS_NOT_SET, _('Not set')),
        (STATUS_REVERTED, _('Reverted')),
    )

    LIMIT_CHECKER = OrderLimitChecker

    name = models.TextField(null=True, blank=True)

    type = models.PositiveSmallIntegerField(null=False, blank=False, choices=ORDER_TYPES)
    operation = models.PositiveSmallIntegerField(choices=OPERATIONS)
    state = models.PositiveSmallIntegerField(choices=list(
        ORDER_STATES.items()), default=0, null=False, blank=False)
    status = models.PositiveSmallIntegerField(default=STATUS_NOT_SET, choices=STATUS_LIST)
    in_transaction = models.ForeignKey(
        Transaction, related_name='order_in_transaction', on_delete=models.CASCADE)
    pair = PairModelField(Pair, on_delete=models.CASCADE)

    executed = models.BooleanField(default=False)

    quantity = MoneyField()
    price = MoneyField(null=True)
    cost = MoneyField(null=True, blank=True)

    price_ts = models.DateTimeField(auto_now_add=True)
    quantity_left = MoneyField()
    # Volume Weighted Average Price
    vwap = MoneyField(default=0)
    # OTC related fields
    otc_limit = MoneyField(blank=True, null=True)
    otc_percent = MoneyField(blank=True, null=True)
    stop = MoneyField(blank=True, null=True)
    in_stack = models.BooleanField(default=True)
    state_changed_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.price is not None and self.price <= 0:
            raise OrderPriceInvalidError()

        if not self.id:
            return self.create_order(*args, **kwargs)

        old_order = type(self).objects.get(pk=self.pk) if self.pk else None
        if old_order and (old_order.state != self.state or old_order.status != self.status):
            OrderStateChangeHistory(
                order=self,
                prev_state=old_order.state,
                prev_status=old_order.status).save()

        return super(Order, self).save(*args, **kwargs)

    def get_balance_in_order(self):
        if self.operation == SELL:
            currency = self.pair.base
        else:
            currency = self.pair.quote

        pair_sum = self.user.order_set.filter(
            state=self.STATE_OPENED,
        ).exclude(
            type__in=[Order.ORDER_TYPE_EXCHANGE, Order.ORDER_TYPE_MARKET]
        ).values(
            'pair'
        ).annotate(
            q_left=Sum(
                Case(
                    When(
                        operation=Order.OPERATION_SELL,
                        then=F('quantity_left')
                    ),
                    default=0,
                    output_field=MoneyField()
                )
            ),
            sum=Sum(
                Case(
                    When(
                        operation=Order.OPERATION_BUY,
                        then=F('quantity_left') * F('price')
                    ),
                    default=0,
                    output_field=MoneyField()
                )
            ),
        )

        amount = to_decimal(0)

        for item in pair_sum:
            pair = Pair.get(item['pair'])
            if pair.base == currency:
                amount += to_decimal(item['q_left'] or 0)
            if pair.quote == currency:
                amount += to_decimal(item['sum'] or 0)

        return to_decimal(amount)

    def create_order(self, *args, **kwargs):
        if self.is_pair_disabled():
            raise CoinOrPairsDisable()

        if self.user.restrictions.disable_orders:
            raise ValidationError('Order creation is restricted', 'user_disable_orders')

        if self.type not in [MARKET, EXCHANGE, ]:
            if self.quantity <= 0:
                raise OrderQuantityInvalidError()

            self.LIMIT_CHECKER.check(self)

        self.check_for_deviation()

        user_id = self.user_id or self.user.id
        self.quantity_left = to_decimal(self.quantity)

        # transaction.set_autocommit(False)

        if self.operation == SELL:
            currency = self.pair.base
            amount = to_decimal(self.quantity)
        else:
            currency = self.pair.quote
            amount = to_decimal(to_decimal(self.quantity) * to_decimal(self.price or 1))

        if self.type in [MARKET, EXCHANGE, ] and self.operation == BUY:
            amount = to_decimal(self.cost)

        with transaction.atomic():

            t = Transaction(reason=REASON_ORDER_OPENED,
                            user_id=user_id,
                            currency=currency,
                            amount=-amount,
                            data={},
                            state=TRANSACTION_COMPLETED
                            )
            t.save(update_balance_on_adding=False, atomic=False)

            self.state = ORDER_OPENED
            self.in_transaction = t
            super(Order, self).save(*args, **kwargs)

            BalanceManager.set_hold(self.user_id, currency, amount, self.get_balance_in_order())

            special_data = {
                'limit': self.otc_limit,
                'percent': self.otc_percent,
            }

            self.add_to_order_change_history(self.price, self.quantity, special_data)

            # transaction.commit()

        if self.id and self.type not in [MARKET, EXCHANGE, STOP_LIMIT]:
            from core.tasks import orders

            data = core_serializer.serialize('json', [self])
            args = [data]
            orders.place_order.apply_async(args, queue=self.queue())

        self.notify()
        return self

    def _revert(self, order, balances, check_balance):
        # TODO check_balance work in transaction.save

        transactions_bulk = []
        revert_bulk = []

        with atomic():
            # return order's hold
            order_transaction = copy_instance(order.in_transaction, Transaction)  # copy model
            order_transaction.revert()  # change reason and amount * -1

            # update user currency balance
            user_balance = balances.get(order_transaction.user_id, {})
            currency_balance = user_balance.get(order_transaction.currency.code, 0)
            currency_balance += order_transaction.amount
            user_balance[order_transaction.currency.code] = currency_balance
            balances[order_transaction.user_id] = user_balance

            try:
                # save transaction
                order_transaction.save(update_balance_on_adding=False, atomic=False)
                # create history
                create_or_update_wallet_history_item_from_transaction(order_transaction)
            except NotEnoughFunds as e:
                raise ValidationError(f'Not enough funds! hold# '
                                      f'order {order.id}, '
                                      f'user {order_transaction.user_id}, '
                                      f'{order_transaction.amount} '
                                      f'{order_transaction.currency}'
                                      )

            # TODO move to bulk
            # transactions_bulk.append(order_transaction)
            revert = OrderRevert(
                user_id=order_transaction.user_id,
                order=order,
                transaction=order_transaction,
                origin_transaction=order.in_transaction,
            )
            # revert.save()
            revert_bulk.append(revert)

        with atomic():
            # update orders
            extra_transactions = Transaction.objects.filter(
                data__order_id=order.id,
                user_id=order.user_id,
                state=TRANSACTION_COMPLETED
            )

            for extra_transaction_origin in extra_transactions:
                extra_transaction = copy_instance(extra_transaction_origin, Transaction)
                extra_transaction.revert()

                user_balance = balances.get(extra_transaction.user_id, {})
                currency_balance = user_balance.get(extra_transaction.currency.code, 0)
                currency_balance += extra_transaction.amount
                user_balance[extra_transaction.currency.code] = currency_balance
                balances[extra_transaction.user_id] = user_balance

                try:
                    extra_transaction.save(update_balance_on_adding=False, atomic=False)
                    create_or_update_wallet_history_item_from_transaction(extra_transaction)
                except NotEnoughFunds as e:
                    raise ValidationError(
                        f'Not enough funds! update_order# '
                        f'order {order.id}, '
                        f'user {extra_transaction.user_id}, '
                        f'{extra_transaction.amount} '
                        f'{extra_transaction.currency}'
                    )

                # TODO move to bulk
                # transactions_bulk.append(extra_transaction)
                revert = OrderRevert(
                    user_id=extra_transaction.user_id,
                    order=order,
                    transaction=extra_transaction,
                    origin_transaction=extra_transaction_origin,
                )
                # revert.save()
                revert_bulk.append(revert)

        with atomic():
            exe_rests = order.executionresult_set.all()

            for exe_res in exe_rests:
                # return order's transactions
                exe_transaction: Transaction = copy_instance(exe_res.transaction, Transaction)
                exe_transaction.revert()

                user_balance = balances.get(exe_transaction.user_id, {})
                currency_balance = user_balance.get(exe_transaction.currency.code, 0)
                currency_balance += exe_transaction.amount
                user_balance[exe_transaction.currency.code] = currency_balance
                balances[exe_transaction.user_id] = user_balance

                try:
                    exe_transaction.save(update_balance_on_adding=False, atomic=False)
                    create_or_update_wallet_history_item_from_transaction(exe_transaction)
                except NotEnoughFunds as e:
                    raise ValidationError(
                        f'Not enough funds! matches# '
                        f'order {order.id}, '
                        f'user {exe_transaction.user_id}, '
                        f'{exe_transaction.amount} '
                        f'{exe_transaction.currency}'
                    )

                # TODO move to bulk
                # transactions_bulk.append(exe_transaction)
                revert = OrderRevert(
                    user_id=order.user_id,
                    order=order,
                    transaction=exe_transaction,
                    origin_transaction=exe_res.transaction,
                    matched_order_id=exe_res.matched_order_id
                )
                # revert.save()
                revert_bulk.append(revert)

                # return matched orders's hold
                exe_transaction_ret: Transaction = copy_instance(exe_res.transaction, Transaction)
                if exe_res.matched_order:
                    exe_transaction_ret.user_id = exe_res.matched_order.user_id
                    exe_transaction_ret.amount += exe_res.fee_amount

                    user_balance = balances.get(exe_transaction_ret.user_id, {})
                    currency_balance = user_balance.get(exe_transaction_ret.currency.code, 0)
                    currency_balance += exe_transaction_ret.amount
                    user_balance[exe_transaction_ret.currency.code] = currency_balance
                    balances[exe_transaction_ret.user_id] = user_balance
                    if exe_transaction_ret.amount < 0:
                        exe_transaction_ret.reason = REASON_ORDER_REVERT_RETURN
                    else:
                        exe_transaction_ret.reason = REASON_ORDER_REVERT_CHARGE

                    try:
                        exe_transaction_ret.save(update_balance_on_adding=False, atomic=False)
                        create_or_update_wallet_history_item_from_transaction(exe_transaction_ret)
                    except NotEnoughFunds as e:
                        raise ValidationError(
                            f'Not enough funds! matched_order_hold# '
                            f'order {order.id}, '
                            f'user {exe_transaction_ret.user_id}, '
                            f'{exe_transaction_ret.amount} '
                            f'{exe_transaction_ret.currency}'
                        )

                    # TODO move to bulk
                    # transactions_bulk.append(exe_transaction_ret)
                    revert = OrderRevert(
                        user_id=exe_transaction_ret.user_id,
                        order=order,
                        transaction=exe_transaction_ret,
                        origin_transaction=exe_res.transaction,
                        matched_order_id=exe_res.matched_order_id
                    )
                    # revert.save()
                    revert_bulk.append(revert)

                cashback_transaction_origin = exe_res.cacheback_transaction

                if cashback_transaction_origin is not None:

                    cashback_transaction = copy_instance(cashback_transaction_origin, Transaction)
                    cashback_transaction.revert()

                    user_balance = balances.get(cashback_transaction.user_id, {})
                    currency_balance = user_balance.get(cashback_transaction.currency.code, 0)
                    currency_balance += cashback_transaction.amount
                    user_balance[cashback_transaction.currency.code] = currency_balance
                    balances[cashback_transaction.user_id] = user_balance
                    try:
                        cashback_transaction.save(update_balance_on_adding=False, atomic=False)
                        create_or_update_wallet_history_item_from_transaction(cashback_transaction)
                    except NotEnoughFunds as e:
                        raise ValidationError(f'Not enough funds! cashback# '
                                              f'order {order.id}, '
                                              f'user {cashback_transaction.user_id}, '
                                              f'{cashback_transaction.amount} '
                                              f'{cashback_transaction.currency}'
                                              )

                    # TODO move to bulk
                    # transactions_bulk.append(cashback_transaction)
                    revert = OrderRevert(
                        user_id=cashback_transaction.user_id,
                        order=order,
                        transaction=cashback_transaction,
                        origin_transaction=cashback_transaction_origin,
                    )
                    # revert.save()
                    revert_bulk.append(revert)

        with atomic():
            # return matched order's transactions
            counter_exe_rests = ExecutionResult.objects.filter(matched_order=order)
            for c_exe_res in counter_exe_rests:
                c_exe_transaction = copy_instance(c_exe_res.transaction, Transaction)
                c_exe_transaction.revert()

                user_balance = balances.get(c_exe_transaction.user_id, {})
                currency_balance = user_balance.get(c_exe_transaction.currency.code, 0)
                currency_balance += c_exe_transaction.amount
                user_balance[c_exe_transaction.currency.code] = currency_balance
                balances[c_exe_transaction.user_id] = user_balance
                try:
                    c_exe_transaction.save(update_balance_on_adding=False, atomic=False)
                    create_or_update_wallet_history_item_from_transaction(c_exe_transaction)
                except NotEnoughFunds as e:
                    raise ValidationError(f'Not enough funds! matched_order_transaction# '
                                          f'order {order.id}, '
                                          f'user {c_exe_transaction.user_id}, '
                                          f'{c_exe_transaction.amount} '
                                          f'{c_exe_transaction.currency}'
                                          )

                # TODO move to bulk
                # transactions_bulk.append(c_exe_transaction)
                revert = OrderRevert(
                    user_id=c_exe_transaction.user_id,
                    order_id=c_exe_res.order_id,
                    transaction=c_exe_transaction,
                    origin_transaction=c_exe_res.transaction,
                    matched_order_id=c_exe_res.matched_order_id
                )
                # revert.save()
                revert_bulk.append(revert)

        with atomic():
            # TODO transaction bulk
            # Transaction.objects.bulk_create(transactions_bulk)
            OrderRevert.objects.bulk_create(revert_bulk)

        order.state = Order.STATE_REVERT
        order.status = Order.STATUS_REVERTED
        order.save()

        return balances

    def revert(self, balances=dict, check_balance=True):
        if self.status == self.STATUS_REVERTED:
            raise ValidationError(f'the order {self.id} has already been reverted!')

        if self.state not in [Order.STATE_CLOSED, Order.STATE_CANCELLED]:
            raise ValidationError(f'the order {self.id} was not closed or not canceled!')

        if not self.executed:
            raise ValidationError(f'the order {self.id} was not executed!')

        return self._revert(self, balances, check_balance)

    def delete(self, using=None, keep_parents=False, by_admin=False):
        if by_admin:
            order_types = []
        else:
            order_types = [MARKET, EXCHANGE]

        if settings.ORDER_DELETE_ATTEMPT_CACHE:  # cache prevent multiple cancels. cause bots
            # TODO: make a review
            key = f'front_oncancel-{self.id}'
            if key in cache:
                log.warning(f'{self.id} already on cancel')
                return

        if self.type in order_types:
            raise CanNotCancelMarketOrder()
        if self.state != ORDER_OPENED:
            raise ValidationError('can not cancel not opened order!', "open_order_cant_cancel")
        args = [{'order_id': self.id}]
        from core.tasks import orders

        if settings.ORDER_DELETE_ATTEMPT_CACHE:
            cache.set(key, True, 120)

        orders.cancel_order.apply_async(args, queue=self.queue())

    def update_order(self, order_data, nowait=False):
        if self.is_pair_disabled():
            raise CoinOrPairsDisable()

        if self.state != ORDER_OPENED:
            raise OrderNotOpenedError(order=self)
        quantity = order_data.get('quantity') or self.quantity
        price = order_data.get('price') or self.price

        self.check_for_deviation(price)

        if self.operation == SELL:
            currency = self.pair.base
            amount = to_decimal(quantity)
        else:
            currency = self.pair.quote
            amount = to_decimal(quantity) * to_decimal(price or 1)
        min_quantity = get_min_quantity(currency)
        if quantity and amount < min_quantity:
            raise OrderQuantityInvalidError(_(f'`Minimal quantity: {min_quantity} {currency.code}.'))

        args = [order_data]
        from core.tasks import orders
        f = orders.update_order_wrapped.apply_async(args, queue=self.queue())

        if nowait:
            return

        return f.get(timeout=50)

    def _update_order(self, order_data):
        if self.state != ORDER_OPENED:
            raise OrderNotOpenedError(order=self)

        if self.type not in [EXTERNAL, LIMIT, STOP_LIMIT]:
            raise OrderUnknownTypeError()

        is_otc_order = order_data.get('otc_percent') or order_data.get('otc_percent')
        if is_otc_order:
            if self.type != EXTERNAL:
                raise ValidationError({
                    'message': 'special data is valid only for OTC!',
                    'type': 'wrong_data'
                })

            self.otc_percent = order_data.get(
                'otc_percent') and to_decimal(order_data.get('otc_percent'))
            self.otc_limit = order_data.get('otc_limit') and to_decimal(order_data.get('otc_limit'))

        price = to_decimal(order_data.get('price', self.price))
        stop = order_data.get('stop', self.stop)
        stop = to_decimal(stop) if stop else stop
        quantity = to_decimal(order_data.get('quantity', self.quantity))
        is_external = order_data.get('is_external')
        special_data = {
            'percent': self.otc_percent,
            'limit': self.otc_limit,
            'stop': self.stop,
        }

        if price <= 0:
            raise OrderPriceInvalidError()

        log.info(
            f'order update: {self.id}, '
            f'qty: {self.quantity}, '
            f'price: {self.price}, '
            f'new qty: {quantity}, '
            f'new price: {price}, '
            f'new stop: {stop}'
        )
        if self.price == price and self.quantity == quantity and self.stop == stop:
            if is_otc_order:
                self.save(update_fields=['otc_percent', 'otc_limit'])  # need for signal
                self.add_to_order_change_history(price, quantity, special_data)
            return

        quantity_executed = self.quantity - self.quantity_left
        new_quantity_left = quantity - quantity_executed

        if new_quantity_left <= 0:
            raise OrderQuantityInvalidError()

        with atomic():
            if self.operation == BUY:
                currency = self.pair.quote
                volume = to_decimal(to_decimal(self.quantity_left) * to_decimal(self.price))
                new_volume = to_decimal(to_decimal(new_quantity_left) * to_decimal(price))
                amount = volume - new_volume
            else:
                currency = self.pair.base
                amount = to_decimal(self.quantity) - to_decimal(quantity)
                new_volume = to_decimal(quantity)

            self.LIMIT_CHECKER.check_cost(currency, new_volume, self.pair, self.id)

            self.price = price
            self.stop = stop
            self.quantity_left = new_quantity_left
            self.quantity = quantity
            super(Order, self).save()

            if amount != 0:
                reason = REASON_ORDER_EXTRA_CHARGE if amount < 0 else REASON_ORDER_CHARGE_RETURN
                t = Transaction(reason=reason,
                                user_id=self.user_id,
                                currency=currency,
                                amount=amount,
                                data={'order_id': self.id},
                                state=TRANSACTION_COMPLETED
                                )
                t.save(update_balance_on_adding=False, atomic=False)

                if reason == REASON_ORDER_EXTRA_CHARGE:
                    BalanceManager.set_hold(self.user_id, currency, amount,
                                            self.get_balance_in_order())
                else:
                    BalanceManager.free_hold(self.user_id, currency, amount,
                                             self.get_balance_in_order())
            if not is_external:
                self.add_to_order_change_history(price, quantity, special_data)

        self.notify(is_updated=True)

    def cancel_order(self):
        # call only with task!
        if not self.state == ORDER_OPENED:
            log.debug(f'Cancel failed. Order {self.id} not opened')
            return

        with transaction.atomic():
            r = ExecutionResult(order=self,
                                user_id=self.user_id,  # ?
                                cancelled=True,
                                price=self.price,
                                quantity=self.quantity_left,
                                pair=self.pair,
                                )
            r.transaction = self.transaction(REASON_ORDER_CANCELED, self.quantity_left, self.price)

            r.save()
            self.state = ORDER_CANCELED
            self.save()

            if r.transaction:
                BalanceManager.free_hold(
                    self.user_id,
                    r.transaction.currency,
                    r.transaction.amount,
                    self.get_balance_in_order()
                )

            order_changed.send(sender=self.__class__, order=self)

        from core.tasks.orders import send_api_callback

        send_api_callback(self.user_id, self.id)

        self.notify(is_cancelled=True)

    def determine_price(self, order):
        """ `self` is newcome order to process,
            `order` is order already presents in stack
             market always has the best price
             limit has the average price
        """
        # price is the price of order already in stack (older)
        return to_decimal(order.price)

    def quantity_from_cost(self, order):
        quantityt_left = to_decimal(self.cost)
        target_quantity = 0

        price = to_decimal(order.price)
        qty = to_decimal(order.quantity_left)

        quoted_amount = price * qty
        q = min([quantityt_left, quoted_amount])
        target_quantity += q / price
        quantityt_left -= q

        return target_quantity

    def get_vwap(self, quantity, price):
        cost = to_decimal(to_decimal(quantity) * to_decimal(price))
        if self.quantity and self.price:
            cost += to_decimal(to_decimal(self.quantity) * to_decimal(self.price))
            quantity += to_decimal(self.quantity)
        result = to_decimal(cost / quantity)
        return result

    def execute(self, order):
        from core.tasks.orders import send_api_callback

        # transaction.set_autocommit(False)

        with transaction.atomic():
            assert self.operation != order.operation, 'Operations should be different!'
            if self.type in [MARKET, EXCHANGE, ] and self.operation == BUY:
                quantity = to_decimal(min(self.quantity_from_cost(order), order.quantity_left))
            else:
                quantity = to_decimal(min(self.quantity_left, order.quantity_left))
            price = self.determine_price(order)  # TODO: better price determination

            self._execute(matched=order, quantity=quantity, price=price)
            order._execute(matched=self, quantity=quantity, price=price)

        order_changed.send(sender=self.__class__, order=self)
        order_changed.send(sender=self.__class__, order=order)
        # transaction.commit()

        send_api_callback(self.user_id, self.id)
        send_api_callback(order.user_id, order.id)

        if self.type == self.ORDER_TYPE_LIMIT:
            last_pair_price_cache.set(self.pair, self.price)

    def _execute(self, matched, quantity, price):
        quantity = to_decimal(quantity)
        price = to_decimal(price)

        if self.type in [MARKET, EXCHANGE, ]:
            if self.operation == BUY:
                self.cost -= to_decimal(price * quantity)
                self.quantity += quantity
            else:
                self.quantity_left -= quantity

            self.price = self.get_vwap(quantity, price)
        else:
            self.quantity_left -= quantity

        self.quantity_left = to_decimal(self.quantity_left)

        r = ExecutionResult(order=self,
                            user_id=self.user_id,  # ?
                            price=price,
                            quantity=quantity,
                            matched_order=matched,
                            pair=self.pair,
                            fee_rate=to_decimal(self.get_fee()),
                            matched_order_price=to_decimal(matched.price or 1),
                            )

        if self.operation == BUY and self.type not in [MARKET, EXCHANGE, ]:
            r.cacheback_transaction = self.transaction(REASON_ORDER_CACHEBACK, quantity, price)

            if r.cacheback_transaction is not None:
                # self.pair.quote increase
                BalanceManager.free_hold(
                    self.user_id,
                    self.pair.quote,
                    r.cacheback_transaction.amount,
                    self.get_balance_in_order()
                )

        r.transaction = self.transaction(REASON_ORDER_EXECUTED, quantity, price)
        amount = self.get_executed_amount(quantity, price)
        r.fee_amount = self.calculate_fee_amount(amount)
        # try:

        if r.transaction is None:
            # something goes wrong
            log.error("Try to cancel order #%s due execution error", self.id)

            from core.tasks.orders import cancel_order
            cancel_order.apply([{
                'order_id': self.id,
            }])
            return

        # except Exception:
        #     log.exception('Unknown error')
        #     return

        r.save()

        self.executed = True
        if (self.type in [MARKET, EXCHANGE, ] and self.cost == to_decimal(0)) or \
                (to_decimal(self.quantity_left) == to_decimal(0)):
            self.state = ORDER_CLOSED

        # todo: findout reason
        if to_decimal(self.quantity_left) == 0:
            self.state = ORDER_CLOSED

        self.save()

        if self.operation == Order.OPERATION_SELL:
            BalanceManager.spend_hold(self.user_id, self.pair.base, self.get_balance_in_order())
        else:
            BalanceManager.spend_hold(self.user_id, self.pair.quote, self.get_balance_in_order())

        BalanceManager.increase_amount(self.user_id, r.transaction.currency, r.transaction.amount)
        self.notify(is_executed=True, matched_amount=amount)

    def transaction(self, reason, quantity, price):
        quantity = to_decimal(quantity)
        price = to_decimal(price or 1)

        t = Transaction(user_id=self.user_id,
                        reason=reason,
                        state=TRANSACTION_COMPLETED
                        )

        if reason == REASON_ORDER_EXECUTED:
            t.currency = self.pair.base if self.operation == BUY else self.pair.quote
            t.amount = self.get_executed_amount(quantity, price)
            t.amount = to_decimal(t.amount - self.calculate_fee_amount(t.amount))
        elif reason == REASON_ORDER_CANCELED:
            t.currency = self.pair.base if self.operation == SELL else self.pair.quote
            if self.type in [MARKET, EXCHANGE, ]:
                t.amount = to_decimal(quantity if self.operation == SELL else self.cost)
            else:
                t.amount = to_decimal(quantity if self.operation ==
                                      SELL else to_decimal(quantity) * to_decimal(price))
        elif reason == REASON_ORDER_CACHEBACK:
            assert self.operation == BUY, 'No cacheback for SELL operation!'
            t.currency = self.pair.quote
            t.amount = to_decimal((self.price - price) * quantity)

        else:
            raise ValidationError({
                'message': 'Bad reason',
                'reason': reason,
                'type': 'bad_reason'
            })
        t.amount = to_decimal(t.amount)
        if t.amount == 0:
            return None
        t.save(update_balance_on_adding=False, atomic=False)
        return t

    def add_to_order_change_history(self, price, quantity, special_data=None):
        data = {
            'price': price,
            'quantity': quantity,
            'order': self
        }
        if special_data:
            data['otc_percent'] = special_data.get(
                'percent') and to_decimal(special_data.get('percent'))
            data['otc_limit'] = special_data.get('limit') and to_decimal(special_data.get('limit'))
            data['stop'] = special_data.get('stop') and to_decimal(special_data.get('stop'))
        OrderChangeHistory(**data).save()

    def get_executed_amount(self, quantity, price):
        return to_decimal(quantity if self.operation == BUY else quantity * price)

    def calculate_fee_amount(self, amount):
        # if user have 0 fee
        fee_rate = self.get_fee()
        if fee_rate == 0:
            return to_decimal(0)

        fee_amount = to_decimal(amount * self.get_fee())
        if fee_amount < MIN_FEE_AMOUNT:
            fee_amount = MIN_FEE_AMOUNT

        return fee_amount

    def get_fee(self):
        return to_decimal(Profile.get_fee_by_user(self.user_id, self))

    @property
    def operation_str(self):
        return OPERATIONS[self.operation]

    @property
    def type_str(self):
        return ORDER_TYPES[self.type]

    def __str__(self):
        model_data = model_to_dict(self)
        model_data.update({
            "operation": self.operation_str,
            "type": self.type_str,
            "pair": self.pair.code
        })

        return '<{id}:{pair}:{operation}:q{quantity_left}:p{price}>'.format(**model_data)

    def queue(self):
        return 'orders.{}'.format(self.pair.code.upper())

    def _money_in(self):
        total = self.changes_history.all().aggregate(sum=Sum('transaction__amount'))
        return total

    def _money_out(self):
        qs = self.executionresult_set.all()
        agg = Sum(F('quantity') * F('price')) if self.operation == BUY else Sum('quantity')
        results = qs.aggregate(volume=agg, back=Sum('cacheback_transaction__amount'))
        return results['volume'] or 0, results['back'] or 0

    def _money_in_order(self):
        if self.state == ORDER_CANCELED:
            return 0
        if self.operation == SELL:
            return self.quantity_left
        else:
            return to_decimal(self.quantity_left * self.price)

    #  TODO remove ?
    def _balance(self):
        return sum([self._money_in(), sum(self._money_out()), self._money_in_order()])

    def is_pair_disabled(self):
        if not PairSettings.is_pair_enabled(self.pair):
            return True
        if self.type in [LIMIT, MARKET, EXTERNAL]:
            return is_coin_disabled(self.pair.base.code, DISABLE_STACK) or \
                is_coin_disabled(self.pair.quote.code, DISABLE_STACK)
        if self.type == EXCHANGE:
            return is_coin_disabled(self.pair.base.code, DISABLE_EXCHANGE) or \
                is_coin_disabled(self.pair.quote.code, DISABLE_EXCHANGE)
        return False

    def notify(self, is_executed=False, is_updated=False, is_cancelled=False, matched_amount=Decimal('0.0')):
        from exchange.notifications import opened_orders_notificator
        from exchange.notifications import opened_orders_by_pair_notificator

        if is_executed:
            from exchange.notifications import executed_order_notificator
            executed_order_notificator.add_data(entry=self, user_id=self.user_id, matched_amount=matched_amount)

        if is_executed or is_cancelled:
            opened_orders_notificator.add_data(entry=self, delete=True)
            opened_orders_by_pair_notificator.add_data(entry=self, delete=True)
        else:
            opened_orders_notificator.add_data(entry=self)
            opened_orders_by_pair_notificator.add_data(entry=self)

    def close_market(self):
        # cost only in exchange orders
        if self.type in [EXCHANGE, ]:
            with atomic():
                matched: ExecutionResult = self.executionresult_set.filter(
                    Q(cacheback_transaction=None) & Q(cancelled=False)
                ).order_by('-id', ).first()

                tr = Transaction(
                    user_id=self.user_id,
                    reason=REASON_ORDER_CACHEBACK,
                    state=TRANSACTION_COMPLETED,
                    currency=self.pair.quote,
                    amount=self.cost
                )

                self.cost = None
                self.state = ORDER_CLOSED

                tr.save()
                matched.cacheback_transaction = tr
                matched.save()
                self.save()

    def check_for_deviation(self, price=0):
        if self.type != self.ORDER_TYPE_LIMIT:
            return

        pair_deviation = PairSettings.get_deviation(self.pair)
        if not pair_deviation:
            return

        if not price:
            price = self.price

        last_price = get_pair_last_price(self.pair) or external_exchanges_pairs_price_cache.get(self.pair)
        custom_price = PairSettings.get_custom_price(self.pair)

        if last_price:
            to_compare_price = last_price
        elif custom_price:
            to_compare_price = custom_price
        else:
            raise ValidationError({
                'message': 'no last price and no custom price',
                'type': 'invalid_last_or_custom_price'
            })

        calculated_deviation = calc_relative_percent_difference(to_compare_price, price)
        if calculated_deviation > pair_deviation:
            raise PriceDeviationError(pair=self.pair, deviation=pair_deviation)


class OrderChangeHistory(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='changes_history')
    quantity = MoneyField(null=True, blank=True)
    price = MoneyField(null=True, blank=True)
    otc_percent = MoneyField(null=True, blank=True)
    otc_limit = MoneyField(null=True, blank=True)
    stop = MoneyField(null=True, blank=True)


class OrderStateChangeHistory(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='state_changes_history')
    prev_state = models.PositiveSmallIntegerField(choices=list(ORDER_STATES.items()), default=0, null=False,
                                                  blank=False)
    prev_status = models.PositiveSmallIntegerField(
        default=Order.STATUS_NOT_SET, choices=Order.STATUS_LIST)


class OrderRevert(UserMixinModel, BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_revert', )
    matched_order = models.ForeignKey(
        Order, null=True, on_delete=models.CASCADE, related_name='matched_order_revert', )
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE,
                                    related_name='order_reverted_transaction')
    origin_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='order_origin_transaction',
        null=True,
        blank=True,
    )


class Exchange(UserMixinModel, BaseModel):

    OPERATION_LIST = list(OPERATIONS.items())

    order = models.ForeignKey(Order, on_delete=models.CASCADE,
                              related_name='+', db_constraint=False)
    operation = models.PositiveSmallIntegerField(choices=OPERATION_LIST)
    base_currency = CurrencyModelField()
    quote_currency = CurrencyModelField()
    quantity = MoneyField()
    cost = MoneyField()


class ExecutionResult(UserMixinModel, BaseModel):
    # TODO: do we really need a user here?
    order = models.ForeignKey(Order, on_delete=models.CASCADE, db_constraint=False)
    pair = PairModelField(Pair, on_delete=models.CASCADE)
    matched_order = models.ForeignKey(
        Order, null=True, on_delete=models.CASCADE, related_name='+', db_constraint=False)

    cacheback_transaction = models.ForeignKey(Transaction, null=True, on_delete=models.CASCADE, related_name='+',
                                              db_constraint=False)
    transaction = models.ForeignKey(Transaction, null=True, on_delete=models.CASCADE, related_name='+',
                                    db_constraint=False)
    cancelled = models.BooleanField(default=False)
    quantity = MoneyField()
    fee_rate = MoneyField(default=0)
    price = MoneyField(null=True)
    matched_order_price = MoneyField(null=True)
    fee_amount = MoneyField(default=0)
    fee_aggregate_tx = models.ForeignKey(
        Transaction, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('order', 'matched_order',)

    def to_dict(self):
        return model_to_dict(self)

    @classmethod
    def qs_last_executed(cls, qs):
        return qs.annotate(
            order_gt=F('order_id') - F('matched_order_id'),
        ).filter(
            cancelled=False,
        ).filter(
            order_gt__gt=0,
        ).order_by(
            '-updated',
        )

    @property
    def result_amount(self):
        return to_decimal(
            self.quantity if self.order.operation == BUY else to_decimal(self.quantity) * to_decimal(self.price))

    def get_fee_amount(self):
        return to_decimal(to_decimal(self.result_amount) * to_decimal(self.fee_rate))


# order signal handlers
@receiver(order_changed)
def update_order_vwap(sender, order: Order, **kwargs):
    if order.state in [ORDER_CLOSED, ORDER_CANCELED]:
        log.debug('Updating VWAP for order %s', order.id)

        vwap = order.executionresult_set.filter(
            quantity__gt=0,  # cause we got execution result with no quantity
            cancelled=False,
        ).aggregate(
            vwap=(Sum(F('quantity') * F('price')) / Sum('quantity'))
        )['vwap']

        if vwap is not None:
            Order.objects.filter(id=order.id).update(vwap=vwap)

        from exchange.notifications import closed_orders_notificator
        from exchange.notifications import closed_orders_by_pair_notificator
        closed_orders_notificator.add_data(entry=order)
        closed_orders_by_pair_notificator.add_data(entry=order)

    if order.state != ORDER_OPENED and order.state_changed_at is None:
        Order.objects.filter(id=order.id).update(state_changed_at=timezone.now())

