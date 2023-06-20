import datetime
import logging
from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, F, Count, Q
from django.utils import timezone
from rest_framework.response import Response

from admin_rest import restful_admin as api_admin
from admin_rest.mixins import ReadOnlyMixin, NonPaginatedListMixin
from admin_rest.restful_admin import DefaultApiAdmin
from core.consts.currencies import ALL_CURRENCIES
from core.enums.profile import UserTypeEnum
from core.models import Order
from core.models.inouts.pair import Pair
from core.utils.stats.counters import CurrencyStats
from core.utils.stats.lib import get_prices_in_usd
from dashboard_rest.models import CommonInouts, CommonUsersStats, TradeVolume
from dashboard_rest.models import Topups
from dashboard_rest.models import TradeFee
from dashboard_rest.models import Withdrawals

log = logging.getLogger(__name__)


@api_admin.register(Topups)
class DashboardTopupsAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['created', 'user', 'currency', 'amount', 'state']

    def get_queryset(self):
        return Topups.objects.order_by('-created').prefetch_related('wallet', 'wallet__user')

    def user(self, obj):
        return obj.wallet.user.email


@api_admin.register(Withdrawals)
class DashboardWithdrawalsAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['created', 'user', 'currency', 'amount', 'state']

    def get_queryset(self):
        return Withdrawals.objects.order_by('-created')


@api_admin.register(TradeFee)
class TradeFeeAdmin(ReadOnlyMixin, NonPaginatedListMixin, DefaultApiAdmin):
    list_display = ['currency', 'trade_fee_amount', 'withdrawal_fee_amount']
    filterset_fields = ['created']

    def currency(self, obj):
        """Do not delete"""

    def trade_fee_amount(self, obj):
        """Do not delete"""

    def withdrawal_fee_amount(self, obj):
        """Do not delete"""

    def list(self, request, *args, **kwargs):
        interval = {
            'start': request.query_params.get('created[start]') or datetime.date(datetime.MINYEAR, 1, 1),
            'end': request.query_params.get('created[end]') or datetime.date(datetime.MAXYEAR, 1, 1)
        }
        trade_stats = CurrencyStats.trade_fee(interval)
        withdrawals_stats = CurrencyStats.withdrawals_and_fees(interval)
        res = []
        for currency in ALL_CURRENCIES:
            res.append({
                'currency': currency.code,
                'trade_fee_amount': trade_stats.get(currency, {}).get('total_fee') or 0,
                'withdrawal_fee_amount': withdrawals_stats.get(currency, {}).get('total_fee') or 0,
            })
        return Response({'results': res})


@api_admin.register(CommonUsersStats)
class CommonUsersStatsAdmin(ReadOnlyMixin, NonPaginatedListMixin, DefaultApiAdmin):
    list_display = ['stat_name', 'stat_value']
    filterset_fields = ['date_joined']

    def stat_name(self, obj):
        pass

    def stat_value(self, obj):
        pass

    def list(self, request, *args, **kwargs):
        now = timezone.now()
        interval = {
            'start': request.query_params.get('date_joined[start]') or now - datetime.timedelta(days=1),
            'end': request.query_params.get('date_joined[end]') or datetime.date(datetime.MAXYEAR, 1, 1)
        }
        total_users = CommonUsersStats.objects.filter(
            date_joined__gte=interval['start'],
            date_joined__lte=interval['end'],
        ).aggregate(
            total_users=Count('id'),
        )['total_users'] or 0
        res = [
            {
                'stat_name': 'Users count',
                'stat_value': total_users,
            }
        ]
        return Response({'results': res})


@api_admin.register(CommonInouts)
class CommonInoutsAdmin(ReadOnlyMixin, NonPaginatedListMixin, DefaultApiAdmin):
    list_display = ['currency', 'topups', 'withdrawals']
    filterset_fields = ['created']

    def currency(self, obj):
        pass

    def topups(self, obj):
        pass

    def withdrawals(self, obj):
        pass

    def list(self, request, *args, **kwargs):
        res = []
        now = timezone.now()
        interval = {
            'start': request.query_params.get('created[start]') or now - datetime.timedelta(days=1),
            'end': request.query_params.get('created[end]') or datetime.date(datetime.MAXYEAR, 1, 1)
        }

        prices_in_usd = get_prices_in_usd()
        topups = CurrencyStats.topups(
            interval,
            filter_qs=[~Q(
                Q(user__profile__user_type=UserTypeEnum.staff.value)
                | Q(user__profile__user_type=UserTypeEnum.bot.value)
                | Q(user__email__endswith='@bot.com')
            )],
        )
        withdrawals = CurrencyStats.withdrawals_and_fees(
            interval,
            filter_qs=[~Q(
                Q(user__profile__user_type=UserTypeEnum.staff.value)
                | Q(user__profile__user_type=UserTypeEnum.bot.value)
                | Q(user__email__endswith='@bot.com')
            )],
        )

        total_topus = 0
        total_withdrawals = 0

        for currency in ALL_CURRENCIES:
            usd_price = prices_in_usd.get(currency) or 0

            topups_amount = round(topups.get(currency, {}).get('total_amount') or Decimal('0'), 8)
            topups_amount_usd = round(topups_amount * usd_price, 2)
            withdrawals_amount = round(withdrawals.get(currency, {}).get('total_amount') or Decimal('0'), 8)
            withdrawals_amount_usd = round(withdrawals_amount * usd_price, 2)

            total_topus += topups_amount_usd
            total_withdrawals += withdrawals_amount_usd

            res.append({
                'currency': currency.code,
                'topups': f'{topups_amount.normalize()} (${topups_amount_usd})',
                'withdrawals': f'{withdrawals_amount.normalize()} (${withdrawals_amount_usd})',
            })
        res.append({
            'currency': 'Total',
            'topups': f'${total_topus}',
            'withdrawals': f'${total_withdrawals}',
        })
        return Response({'results': res})


@api_admin.register(TradeVolume)
class TradeVolumeAdmin(ReadOnlyMixin, NonPaginatedListMixin, DefaultApiAdmin):
    list_display = ['pair', 'base_volume', 'quote_volume']
    filterset_fields = ['created']

    def pair(self, obj):
        pass

    def base_volume(self, obj):
        pass

    def quote_volume(self, obj):
        pass

    def list(self, request, *args, **kwargs):
        interval = {
            'start': request.query_params.get('created[start]') or datetime.date(datetime.MINYEAR, 1, 1),
            'end': request.query_params.get('created[end]') or datetime.date(datetime.MAXYEAR, 1, 1)
        }
        qs = TradeVolume.objects.filter(
            ~Q(
                Q(user__profile__user_type=UserTypeEnum.staff.value)
                | Q(user__profile__user_type=UserTypeEnum.bot.value)
                | Q(user__email__endswith='@bot.com')
            ),
            created__gte=interval['start'],
            created__lte=interval['end'],
            cancelled=False,
        ).values('pair').annotate(
            base_volume=Sum(
                Case(
                    When(order__operation=Order.OPERATION_BUY, then=F('quantity')),
                    default=0,
                    output_field=models.DecimalField(),
                )
            ),
            quote_volume=Sum(
                Case(
                    When(order__operation=Order.OPERATION_BUY, then=F('quantity') * F('price')),
                    default=0,
                    output_field=models.DecimalField(),
                )
            ),
        ).order_by('pair')

        volumes_dict = {p['pair']: p for p in qs}

        volumes = []
        for pair in Pair.objects.all():
            volumes.append({
                'pair': pair.code,
                'base_volume': round(volumes_dict.get(pair, {}).get('base_volume', 0), 8),
                'quote_volume': round(volumes_dict.get(pair, {}).get('quote_volume', 0), 8),
            })

        total = Decimal(0)
        prices_in_usd = get_prices_in_usd()

        for i in volumes:
            pair = Pair.get(i['pair'])
            if pair.quote.code == 'USDT':
                vol = i['quote_volume']
            elif pair.base.code == 'USDT':
                vol = i['base_volume']
            elif pair.quote in prices_in_usd:
                vol = prices_in_usd[pair.quote] * i['quote_volume']
            elif pair.base in prices_in_usd:
                vol = prices_in_usd[pair.base] * i['base_volume']

            total += vol

        total = round(total, 2)

        volumes.append({
            'pair': 'Total',
            'base_volume': f'${total}',
            'quote_volume': f'${total}',
        })

        return Response({'results': volumes})


