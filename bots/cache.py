from lib.cache import PrefixedRedisCache

previous_ohlc_period_price_cache = PrefixedRedisCache.get_cache(prefix='previous-ohlc-order-')