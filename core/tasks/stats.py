import datetime

from celery.app import shared_task
from django.conf import settings
from django.db import connection
from django.db.models import Case
from django.db.models import F
from django.db.models import Sum
from django.db.models import When
from django.db.models.fields import DateField
from django.db.models.functions.datetime import Trunc
from django.db.transaction import atomic
from django.utils import timezone
from django.utils.timezone import now

from core.cache import cryptocompare_pairs_price_cache
from core.cache import external_exchanges_pairs_price_cache
from core.consts.orders import BUY
from core.consts.orders import SELL
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.pair_settings import PairSettings
from core.models.orders import ExecutionResult
from core.models.stats import ExternalPricesHistory
from core.models.stats import TradesAggregatedStats
from core.models.stats import UserPairDailyStat
from core.pairs import Pair
from core.pairs import PAIRS
from core.pairs import PAIRS_LIST
from core.tasks.orders import run_otc_orders_price_update
from core.utils.stats.trades_aggregate import TradesAggregator
from lib.batch import BatchProcessor
from lib.batch import chunks
from lib.services.cryptocompare_client import CryptocompareClient
from lib.helpers import calc_relative_percent_difference
from lib.services.exchange_api_client import ExchangeClientSession


class UserStatsBatchProcessor(BatchProcessor):
    def process_batch(self, items):
        UserPairDailyStat.objects.bulk_create(items)

    def make_item(self, obj):

        for k, v in obj.items():
            if v is None:
                obj[k] = 0
        item = UserPairDailyStat(currency1=obj['pair'].base, currency2=obj['pair'].quote, **obj)

        if item.is_empty():
            return None

        return item

    def make_qs(self):
        latest_stat = UserPairDailyStat.objects.all().order_by('-day').first()

        qs = ExecutionResult.objects.filter(cancelled=False).annotate(
            day=Trunc('created', 'day', output_field=DateField())
        )

        if latest_stat:
            qs = qs.filter(day__gt=latest_stat.day)

        qs = qs.filter(day__lt=now().date())
        qs = qs.values(
            'user_id',
            'day',
            'pair'
        )
        qs = qs.annotate(
            volume_got1=Sum(Case(When(order__operation=BUY, then=F('quantity')))),
            volume_got2=Sum(Case(When(order__operation=SELL, then=F('price') * F('quantity')))),
            fee_amount_paid1=Sum(Case(When(order__operation=BUY, then=F('fee_amount')))),
            fee_amount_paid2=Sum(Case(When(order__operation=SELL, then=F('fee_amount')))),
            volume_spent1=Sum(Case(When(order__operation=SELL, then=F('quantity')))),
            volume_spent2=Sum(Case(When(order__operation=BUY, then=F('price') * F('quantity')))),
        )
        qs = qs.order_by('day')
        qs = qs.values(
            'user_id',
            'day',
            'pair',
            'volume_got1',
            'volume_got2',
            'fee_amount_paid1',
            'fee_amount_paid2',
            'volume_spent1',
            'volume_spent2'
        )
        return qs

    def make_batch_iter(self, qs, size):
        return chunks(qs, size)


@shared_task
def make_user_stats():
    with atomic():
        UserStatsBatchProcessor().start()


@shared_task
def update_cryptocompare_pairs_price_cache():
    """
    Get prices from external exchanges and update cache
    """
    pairs = list([Pair.get(pt[1]) for pt in PAIRS_LIST])

    cc_client = CryptocompareClient()

    cc_input_currencies = set()
    cc_output_currencies = set()

    for pair in pairs:
        cc_input_currencies.add(pair.base.code)
        cc_output_currencies.add(pair.quote.code)

    cc_data = cc_client.get_multi_prices(','.join(cc_input_currencies), ','.join(cc_output_currencies))
    for pair in pairs:
        coin_price = cc_data.get(pair.base.code, {}).get(pair.quote.code, 0)
        if coin_price:
            cryptocompare_pairs_price_cache.set(pair, coin_price)


@shared_task
def plan_trades_aggregation(period):
    if not settings.PLAN_TRADES_STATS_AGGRREGATION:
        return
    for pair in PAIRS:
        if DisabledCoin.is_coin_disabled(pair.base.code) or DisabledCoin.is_coin_disabled(pair.quote.code):
            continue
        do_trades_aggregation_for_pair.apply_async((pair.code, period))


@shared_task
def do_trades_aggregation_for_pair(pair, period):
    TradesAggregator(pair, period).start()


@shared_task
def cleanup_old_prices_history():
    week_ago = timezone.now() - datetime.timedelta(days=7)
    res = ExternalPricesHistory.objects.filter(
        created__lt=week_ago,
    ).delete()


@shared_task
def trades_aggregated_cleanup():

    cleanup_to_day = now() - datetime.timedelta(days=settings.STATS_CLEANUP_MINUTE_INTERVAL_DAYS_AGO)

    # delete stats with minute period older than 1 week
    TradesAggregatedStats.objects.filter(
        period=1,  # minute
        ts__lt=cleanup_to_day
    ).delete()


@shared_task
def vacuum_database():
    with connection.cursor() as cursor:
        cursor.execute('VACUUM (ANALYZE, FULL);')


@shared_task
def fill_inout_coin_stats():
    from core.models.stats import InoutsStats
    InoutsStats.refresh()
