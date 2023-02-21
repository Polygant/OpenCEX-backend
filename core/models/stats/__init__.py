import logging
from collections import defaultdict

from django.db import models
from django.db.models import Sum, Q

from core.consts.currencies import ALL_CURRENCIES
from core.currency import CurrencyModelField
from core.enums.profile import UserTypeEnum
from core.pairs import PairModelField
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.fields import MoneyField

log = logging.getLogger(__name__)


class UserPairDailyStat(UserMixinModel, BaseModel):

    pair = PairModelField()

    day = models.DateField()

    currency1 = CurrencyModelField()
    currency2 = CurrencyModelField()

    volume_got1 = MoneyField(default=0)
    volume_got2 = MoneyField(default=0)

    fee_amount_paid1 = MoneyField(default=0)
    fee_amount_paid2 = MoneyField(default=0)

    volume_spent1 = MoneyField(default=0)
    volume_spent2 = MoneyField(default=0)

    def is_empty(self):
        return (self.volume_got1 or self.volume_got2 or self.fee_amount_paid1 or self.fee_amount_paid2 or self.volume_spent1 or self.volume_spent2) == 0

    class Meta:
        unique_together = (("user", "day", 'pair'),)


MINUTE = 1
HOUR = 2
DAY = 3


class TradesAggregatedStats(models.Model):
    PERIODS = {
        'minute': MINUTE,
        'hour': HOUR,
        'day': DAY
    }
    STATS_FIELDS = [
        'min_price',
        'max_price',
        'avg_price',
        'open_price',
        'close_price',
        'volume',
        'amount',
        'num_trades',
        'fee_base',
        'fee_quoted',
    ]

    created = models.DateTimeField(auto_now_add=True)
    pair = PairModelField()
    ts = models.DateTimeField()
    period = models.PositiveSmallIntegerField(choices=[(k[1], k[0]) for k in PERIODS.items()])

    min_price = MoneyField(default=0)
    max_price = MoneyField(default=0)
    avg_price = MoneyField(default=0)

    open_price = MoneyField(default=0)
    close_price = MoneyField(default=0)

    volume = MoneyField(default=0)  # quoted
    amount = models.DecimalField(decimal_places=8, default=0, max_digits=32)  # base currency
    num_trades = models.IntegerField(default=0)

    fee_base = MoneyField(default=0)
    fee_quoted = MoneyField(default=0)

    class Meta:
        unique_together = (['pair', 'ts', 'period'], )


class ExternalPricesHistory(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    pair = PairModelField()
    price = MoneyField(null=True, blank=True)


class InoutsStats(models.Model):
    currency = CurrencyModelField()
    deposits = MoneyField(default=0)
    withdrawals = MoneyField(default=0)

    @classmethod
    def refresh(cls):
        from core.models.inouts.wallet import WalletTransactions
        from core.models.inouts.sci import PayGateTopup
        from core.models.inouts.withdrawal import WithdrawalRequest

        wd_query = (WithdrawalRequest.objects.filter(
            Q(state__in=[
                WithdrawalRequest.STATE_PENDING,
                WithdrawalRequest.STATE_COMPLETED
            ]) |
            (Q(state=WithdrawalRequest.STATE_CREATED) & Q(confirmed=True)),
        ).exclude(
               Q(user__profile__user_type=UserTypeEnum.staff.value)
               | Q(user__profile__user_type=UserTypeEnum.bot.value)
               | Q(user__email__endswith='@bot.com')
               | Q(user__is_staff=True)
        ).values('currency').order_by('currency')).annotate(
            withdrawals=Sum('amount')
        )

        crypto_topups_query = WalletTransactions.objects.filter(
            status=WalletTransactions.STATUS_NOT_SET,
        ).exclude(
            Q(wallet__user__profile__user_type=UserTypeEnum.staff.value)
            | Q(wallet__user__profile__user_type=UserTypeEnum.bot.value)
            | Q(wallet__user__email__endswith='@bot.com')
            | Q(wallet__user__is_staff=True)
        ).values('currency').order_by('currency').annotate(
            topups=Sum('amount')
        )

        paygate_topups_query = PayGateTopup.objects.filter(
            status=PayGateTopup.STATUS_NOT_SET,
            state__in=[PayGateTopup.STATE_COMPLETED]
        ).exclude(
            Q(user__profile__user_type=UserTypeEnum.staff.value)
            | Q(user__profile__user_type=UserTypeEnum.bot.value)
            | Q(user__email__endswith='@bot.com')
            | Q(user__is_staff=True)
        ).values('currency').order_by('currency').annotate(
            topups=Sum('amount')
        )

        withdrawals = defaultdict(int)
        topups = defaultdict(int)

        for wd in wd_query:
            withdrawals[wd['currency'].code] += (wd['withdrawals'] or 0)

        for tp in crypto_topups_query:
            topups[tp['currency'].code] += (tp['topups'] or 0)

        for tp in paygate_topups_query:
            topups[tp['currency'].code] += (tp['topups'] or 0)

        stats = {i.currency: i for i in InoutsStats.objects.all()}

        for currency in ALL_CURRENCIES:
            deps_amount = topups.get(currency.code) or 0
            wds_amount = withdrawals.get(currency.code) or 0
            if currency in stats:
                entry = stats[currency]
                entry.deposits = deps_amount
                entry.withdrawals = wds_amount
            else:
                entry = InoutsStats(
                    currency=currency,
                    deposits=deps_amount,
                    withdrawals=wds_amount
                )
            entry.save()
