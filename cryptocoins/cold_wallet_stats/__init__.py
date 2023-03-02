import datetime
import logging

from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone

from core.models.inouts.sci import PayGateTopup
from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import WithdrawalRequest
from cryptocoins.cold_wallet_stats.bep20_stats_handler import UsdtBnbStatsHandler
from cryptocoins.cold_wallet_stats.bnb_stats_handler import BnbStatsHandler
from cryptocoins.cold_wallet_stats.btc_stats_handler import BtcStatsHandler
from cryptocoins.cold_wallet_stats.erc20_stats_handler import UsdtEthStatsHandler
from cryptocoins.cold_wallet_stats.eth_stats_handler import EthStatsHandler
from cryptocoins.cold_wallet_stats.trc20_stats_handler import UsdtTrxStatsHandler
from cryptocoins.cold_wallet_stats.trx_stats_handler import TrxStatsHandler
from cryptocoins.models.stats import DepositsWithdrawalsStats

log = logging.getLogger(__name__)


CRYPTO_STATS_HANDLERS = [
    BtcStatsHandler,
    EthStatsHandler,
    TrxStatsHandler,
    BnbStatsHandler,
    UsdtEthStatsHandler,
    UsdtBnbStatsHandler,
    UsdtTrxStatsHandler,
]

FIAT_STATS_HANDLERS = [
]


class StatsProcessor:

    @classmethod
    def process(cls, current_stats: DepositsWithdrawalsStats = None, since_daystart=True):
        today = timezone.now()
        if since_daystart:
            today = today.replace(hour=0, minute=0, second=0, microsecond=0)

        if current_stats:
            today = current_stats.created

        previous_entry = DepositsWithdrawalsStats.objects.filter(
            created__lt=today
        ).order_by('-created').first()

        previous_dt = today - datetime.timedelta(days=9999)
        if previous_entry:
            previous_dt = previous_entry.created

        wd_query = (WithdrawalRequest.objects.filter(
            Q(state__in=[
                WithdrawalRequest.STATE_PENDING,
                WithdrawalRequest.STATE_COMPLETED
            ]) |
            (Q(state=WithdrawalRequest.STATE_CREATED) & Q(confirmed=True)),
            created__gte=previous_dt,
            created__lt=today
        ).values('currency', 'data__blockchain_currency').order_by('currency')).annotate(
            withdrawals=Sum('amount')
        )

        crypto_topups_query = WalletTransactions.objects.filter(
            created__gte=previous_dt,
            created__lt=today,
            status=WalletTransactions.STATUS_NOT_SET,
        ).values('currency', 'wallet__blockchain_currency').order_by('currency').annotate(
            topups=Sum('amount')
        )

        paygate_topups_query = PayGateTopup.objects.filter(
            created__gte=previous_dt,
            created__lt=today,
            status=PayGateTopup.STATUS_NOT_SET,
            state__in=[PayGateTopup.STATE_COMPLETED]
        ).values('currency').order_by('currency').annotate(
            topups=Sum('amount')
        )

        withdrawals = {}
        for withdrawal in wd_query:
            currency_code = withdrawal['currency'].code + '_' + \
                            (withdrawal['data__blockchain_currency'] or withdrawal['currency'].code)
            if currency_code in withdrawals:
                withdrawals[currency_code] += (withdrawal['withdrawals'] or 0)
            else:
                withdrawals[currency_code] = (withdrawal['withdrawals'] or 0)

        cryptotopups = {}
        for topup in crypto_topups_query:
            currency_code = topup['currency'].code + '_' + topup['wallet__blockchain_currency'].code
            if currency_code in cryptotopups:
                cryptotopups[currency_code] += (topup['topups'] or 0)
            else:
                cryptotopups[currency_code] = (topup['topups'] or 0)

        fiattopups = {c['currency'].code: c['topups'] for c in paygate_topups_query}

        cold_data = {}
        for handler_class in CRYPTO_STATS_HANDLERS:
            try:
                handler = handler_class()
                res = handler.get_calculated_data(today, previous_dt, previous_entry, cryptotopups, withdrawals)
                cold_data.update(res)
            except Exception as e:
                log.exception(f'Cant fetch cold wallet stats for {handler_class}')

        for handler_class in FIAT_STATS_HANDLERS:
            try:
                handler = handler_class()
                res = handler.get_calculated_data(today, previous_dt, previous_entry, fiattopups, withdrawals)
                cold_data.update(res)
            except Exception as e:
                log.exception(f'Cant fetch stats for {handler_class}')

        if current_stats:
            DepositsWithdrawalsStats.objects.filter(id=current_stats.id).update(stats=cold_data)
        else:
            DepositsWithdrawalsStats.objects.create(created=today, stats=cold_data)
