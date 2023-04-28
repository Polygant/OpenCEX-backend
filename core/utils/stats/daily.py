from django.db.models import F
from django.db.models import Sum
from django.utils import timezone

from core.cache import PAIRS_VOLUME_CACHE_KEY
from core.cache import last_pair_price_cache
from core.cache import orders_app_cache
from core.pairs import PAIRS, Pair


def get_pair_last_price(pair):
    """Get latest price of selected pair via last match"""
    last_price = last_pair_price_cache.get(pair)
    if last_price is not None:
        return last_price

    if not Pair.exists(pair):
        return 0

    from core.models.orders import ExecutionResult
    res = ExecutionResult.objects.filter(
        pair=pair,
        cancelled=False
    ).order_by('-created').only('price').first()
    price = res.price if res else 0

    last_pair_price_cache.set(pair, price)

    return price


def get_last_prices(ts=None):
    from core.models.orders import ExecutionResult

    resultq = {}
    for pair in PAIRS:
        q = ExecutionResult.objects.filter(pair=pair, cancelled=False)
        if ts:
            q = q.filter(created__lte=ts)
        q = q.order_by('-created').values('pair', 'price', 'id', 'created')
        item = q.first()
        resultq[pair.code] = item['price'] if item else None

    return resultq


def get_pairs_24h_stats() -> dict:
    """Returns pairs 24h stats"""
    from core.models.orders import ExecutionResult
    from core.models.inouts.pair_settings import PairSettings

    volume = Sum(F('price') * F('quantity'))

    ts_24h_ago = timezone.now().replace(
        second=0,
        microsecond=0,
    ) - timezone.timedelta(hours=24)

    qs = ExecutionResult.objects.filter(
        order__operation=1, # count only one operation, other case volume should be /2!
        cancelled=False,
        updated__gte=ts_24h_ago
    ).values('pair').annotate(
        volume=volume,
        base_volume=Sum('quantity')
    )

    volumes = {i['pair'].code: i['volume'] for i in qs}
    base_volumes = {i['pair'].code: i['base_volume'] for i in qs}

    last_prices = get_last_prices()
    prices_24h = get_last_prices(ts_24h_ago)

    result = []
    for pair in PAIRS:
        price = last_prices.get(str(pair), None)
        price24 = prices_24h.get(str(pair), None)
        price_24_value = 0
        if price is not None and price24 is not None:
            price_24_value = price - price24
        if not price:
            trend = 0
        elif not price24:
            trend = 100
        else:
            trend = 100 * (price - price24) / price24
        pair_data = pair.to_dict()
        pair_data['stack_precisions'] = PairSettings.get_stack_precisions_by_pair(pair.code)
        result.append({
            'volume': volumes.get(str(pair), None),
            'base_volume': base_volumes.get(str(pair), None),
            'price': price,
            'price_24h': trend,  # price 24h percent
            'price_24h_value': price_24_value,  # price 24h value
            'pair': str(pair),
            'pair_data': pair_data,
        })

    return {
        'pairs': result,
    }


def get_filtered_pairs_24h_stats(disabled_type=None):
    """Returns pairs 24h stats excluding disabled pairs and coins"""
    from core.models import DisabledCoin
    from core.models import PairSettings

    pairs_data = orders_app_cache.get(PAIRS_VOLUME_CACHE_KEY) or get_pairs_24h_stats()
    allowed_pairs = []
    for pair in pairs_data['pairs']:
        base, quote = pair['pair'].split('-')

        if not PairSettings.is_pair_enabled(pair['pair']):
            continue

        if DisabledCoin.is_coin_disabled(base, disabled_type) or DisabledCoin.is_coin_disabled(quote, disabled_type):
            continue
        allowed_pairs.append(pair)

    pairs_data['pairs'] = allowed_pairs
    return pairs_data
