import logging

from django.contrib.auth.models import User
from django.db.models import F
from django.db.models.aggregates import Count
from django.db.models.aggregates import Sum
from django.db.models.expressions import Case
from django.db.models.expressions import When
from django.db.models.fields import IntegerField
from rest_framework.exceptions import ValidationError

from core.consts.orders import BUY
from core.consts.orders import SELL
from core.consts.currencies import ALL_CURRENCIES
from core.models.inouts.balance import Balance
from core.models.inouts.pair import Pair
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import Transaction
from core.models.inouts.withdrawal import COMPLETED
from core.models.inouts.withdrawal import WithdrawalRequest
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.utils.stats.lib import ExchangeQuerySetStats
from core.utils.stats.lib import TradeVolumeForPeriod
from core.utils.stats.lib import get_prices_in_usd
from core.utils.stats.lib import qs_filter_interval
from lib.helpers import to_decimal

logger = logging.getLogger(__name__)


class EntityStatsForPeriod:
    ENTITIES = {
        'users': (User.objects.all(), 'date_joined', Count('id')),
        'orders': (Order.objects.all(), 'created', Count('id')),
        'topups': (Transaction.objects.filter(reason=REASON_TOPUP), 'created', Count('id')),
        'withdrawals': (WithdrawalRequest.objects.all(), 'created', Count('id')),
    }

    QSS_CLASS = ExchangeQuerySetStats

    @classmethod
    def get(cls, entity, period):
        if entity not in cls.ENTITIES:
            raise ValidationError({
                'message': f'Bad entity {entity}',
                'type': 'bad_entity'
            })

        qs, field, aggregate = cls.ENTITIES[entity]
        qss = cls.QSS_CLASS(qs, field, aggregate)

        if isinstance(period, dict):
            return qss.for_range(period['start'], period['end'])
        if period not in cls.QSS_CLASS.PERIODS():
            raise ValidationError({
                'message': f'Bad period {period}',
                'type': 'bad_period'
            })

        return qss.for_interval(period)


class CurrencyStats:
    @classmethod
    def withdrawals_and_fees(cls, interval, filter_qs=None):
        if filter_qs is None:
            filter_qs = []

        result = {
            i: {
                'currency': i,
                'total_amount': 0,
                'total_fee': 0,
                'count': 0
            }
            for i in ALL_CURRENCIES
        }
        qs = WithdrawalRequest.objects.filter(
            *filter_qs,
            approved=True,
            confirmed=True,
            state=COMPLETED,
        )

        qs = qs_filter_interval(qs, interval, 'updated')

        qs = qs.values('currency').annotate(
            total_amount=Sum('amount'),
            total_fee=Sum('our_fee_amount'),
            count=Count('id')
        )

        for i in qs:
            result[i['currency']] = i

        # return sorted(result.values(), key=lambda x: x['currency'].code)
        return result

    @classmethod
    def topups(cls, interval, filter_qs=None):
        if filter_qs is None:
            filter_qs = []

        qs = Transaction.objects.filter(*filter_qs, reason=REASON_TOPUP)
        qs = qs_filter_interval(qs, interval)
        qs = qs.values('currency').annotate(
            total_amount=Sum('amount'),
            count=Count('id')
        )
        return {i['currency']: i for i in qs}

    @classmethod
    def overall(cls, interval):
        result = {
            i: {
                'topups': {},
                'withdrawals': {},
                'fee': {}}
            for i in ALL_CURRENCIES
        }

        for i in cls.topups(interval):
            result[i['currency']]['topups'] = i

        for i in cls.withdrawals_and_fees(interval):
            result[i['currency']]['withdrawals'] = i

        for i in cls.trade_fee(interval):
            result[i['transaction__currency']]['fee'] = i
        return result

    @classmethod
    def trade_fee(cls, interval):
        result = {
            i: {
                'currency': i,
                'total_fee': 0
            }
            for i in ALL_CURRENCIES
        }

        qs = ExecutionResult.objects.filter(
            cancelled=False,
            fee_amount__gt=0,
        )

        qs = qs_filter_interval(qs, interval, 'created')

        qs = qs.values(
            'transaction__currency'
        ).annotate(
            total_fee=Sum('fee_amount'),
            currency=F('transaction__currency'),
        )

        for i in qs:
            result[i['currency']] = i

        # return sorted(result.values(), key=lambda x: x['currency'].code)
        return result

    @classmethod
    def trade_fee_total_usd(cls, interval):
        prices_in_usd = get_prices_in_usd()
        total = to_decimal(0)
        for i in cls.trade_fee(interval):
            if i['currency'] not in prices_in_usd:
                continue
            total += i['total_fee'] * prices_in_usd[i['currency']]

        return total

    @classmethod
    def withdrawal_fee_total_usd(cls, interval):
        prices_in_usd = get_prices_in_usd()
        total = to_decimal(0)
        for i in cls.withdrawals_and_fees(interval):
            if i['currency'] not in prices_in_usd:
                continue
            total += i['total_fee'] * prices_in_usd[i['currency']]

        return total


class BalancesStats:
    @classmethod
    def user_balances(cls) -> list:
        q = Balance.objects.all()
        q = q.values('currency').annotate(
            total_free=Sum('amount'),
            total_in_orders=Sum('amount_in_orders'),
            total=Sum(F('amount') + F('amount_in_orders'))
        )
        return list(q)


class TradeStats:
    @classmethod
    def get_volumes(cls, interval):
        tv = TradeVolumeForPeriod()
        volumes = list(tv.all_pairs(interval))
        total = tv.total_in_usd(interval, volumes)

        result = {pair: {} for pair in Pair.objects.all()}

        for i in volumes:
            result[i['pair']] = i

        return {
            'volumes': result,
            'total': total
        }

    @classmethod
    def orders(cls, interval):
        qs = Order.objects.all()
        qs = qs_filter_interval(qs, interval)
        qs = qs.values('pair').annotate(
            sells=Count(Case(When(operation=SELL, then=1), output_field=IntegerField())),
            buys=Count(Case(When(operation=BUY, then=1), output_field=IntegerField())),
            total=Count('id')
        )
        return qs

    @classmethod
    def volumes_with_orders(cls, interval):
        volumes = cls.get_volumes(interval)
        orders = {i['pair']: i for i in cls.orders(interval)}

        for pair, v in volumes['volumes'].items():
            v['orders'] = orders.get(pair)

        return volumes
