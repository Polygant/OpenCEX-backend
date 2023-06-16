import decimal
from datetime import timedelta

import cachetools.func
from dateutil.relativedelta import relativedelta
from django.db.models import F
from django.db.models.aggregates import Sum
from django.utils.timezone import now
from qsstats import QuerySetStats
from qsstats.utils import get_bounds

from core.currency import Currency
from core.models.stats import TradesAggregatedStats, MINUTE
from core.models.inouts.pair import Pair
from core.utils.stats.daily import get_last_prices


class ExchangeQuerySetStats(QuerySetStats):
    BASIC_INTERVALS = [
        'day',
        'week',
        'year',
        'month',
        'hour',
        'minute'
    ]

    LASTS = {
        '24h': relativedelta(hours=24),
        '3month': relativedelta(months=3),
        '6month': relativedelta(months=6),
    }

    @classmethod
    def PERIODS(cls) -> list:
        frames = []
        frames += cls.BASIC_INTERVALS
        frames += ['previous_%s' % i for i in cls.BASIC_INTERVALS]
        frames += ['last_%s' % i for i in cls.LASTS]
        frames += ['alltime']
        return frames

    @classmethod
    def bounds_for_interval(cls, interval, dt=None):
        dt = dt or now()

        if isinstance(interval, dict):
            return interval['start'], interval['end']

        if interval.startswith('previous_'):
            interval = interval.split('previous_')[-1]
            start, end = get_bounds(dt, interval)
            dt = start - timedelta(seconds=1)
            return get_bounds(dt, interval)

        if interval.startswith('last_'):
            interval = interval.split('last_')[-1]

            end = now()
            start = end - cls.LASTS[interval]
            return start, end

        if interval == 'alltime':
            return None, None

        return get_bounds(dt, interval)

    def for_interval(self, interval: str, dt=None, date_field=None, aggregate=None):
        date_field = date_field or self.date_field
        dt = dt or now()
        start, end = self.bounds_for_interval(interval, dt)
        kwargs = {}
        if start and end:
            kwargs = {'%s__range' % date_field: (start, end)}
        return self._aggregate(date_field, aggregate, kwargs)


@cachetools.func.ttl_cache(ttl=5)
def get_prices_in_usd():
    """ converts last prices to usd prices for all currencies in system """
    prices = {
        Currency.get('USDT'): 1
    }

    non_usd_pairs = []
    # find prices for pairs in usd
    for k, price in get_last_prices().items():
        if not price:
            continue
        pair = Pair.get(k)
        if pair.quote.code == 'USDT':
            prices[pair.base] = price
        elif pair.base.code == 'USDT':
            prices[pair.quote] = 1 / price
        else:
            non_usd_pairs.append((pair, price))

    cnt = 0
    while non_usd_pairs or cnt < 10:
        cnt += 1
        if not non_usd_pairs:
            break
        pair, price = non_usd_pairs.pop()
        if pair.quote in prices and pair.base in prices:
            # price already determined
            continue

        if pair.quote in prices:
            in_usd = prices[pair.quote]
            prices[pair.base] = (price * in_usd)
        elif pair.base in prices:
            in_usd = prices[pair.base]
            prices[pair.quote] = 1 / (price / in_usd)
        else:
            non_usd_pairs.append((pair, price))
    return prices


def qs_filter_interval(qs, interval, field='created'):
    start, end = ExchangeQuerySetStats.bounds_for_interval(interval)
    if start and end:
        filt = {f'{field}__range': (start, end)}
        qs = qs.filter(**filt)
    return qs


class TradeVolumeForPeriod:
    def for_pair(self, pair, interval):
        qs = self.base_qs()
        qs = qs_filter_interval(qs, interval, 'ts')
        qs = qs.filter(pair=pair)
        return qs.annotate(** self.aggregates())

    @classmethod
    def base_qs(cls):
        return TradesAggregatedStats.objects.filter(
            period=MINUTE,
        )

    def aggregates(self):
        return dict(
            base=Sum(F('amount')),
            quoted=Sum(F('volume')),
            fee_base=Sum(F('fee_base')),
            fee_quoted=Sum(F('fee_quoted')),
        )

    def all_pairs(self, interval):
        qs = self.base_qs()
        qs = qs_filter_interval(qs, interval)
        qs = qs.values('pair')
        return qs.annotate(** self.aggregates())

    def total_in_usd(self, interval, volumes=None):
        usd_prices = get_prices_in_usd()
        volumes = self.all_pairs(interval) if volumes is None else volumes
        total = decimal.Decimal(0)

        for i in volumes:
            pair = i['pair']
            if pair.quote.code == 'USDT':
                vol = i['quoted']
            elif pair.base.code == 'USDT':
                vol = i['base']
            elif pair.quote in usd_prices:
                vol = usd_prices[pair.quote] * i['quoted']
            elif pair.base in usd_prices:
                vol = usd_prices[pair.base] * i['base']

            total += vol
        return total
