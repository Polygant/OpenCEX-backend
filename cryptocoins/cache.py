from lib.cache import PrefixedRedisCache


sat_per_byte_cache = PrefixedRedisCache.get_cache(prefix='public-cryptocoins-sat_per_byte-cache-')
