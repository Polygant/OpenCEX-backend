from cachetools import TTLCache
from django.conf import settings

from lib.cache import PrefixedRedisCache

PAIRS_VOLUME_CACHE_KEY = 'pairs-volume'
API_CALLBACK_CACHE_KEY = 'api-callback'
KEEPER_BALANCES_CACHE_KEY = 'keep_balances'
RESEND_VERIFICATION_TOKEN_CACHE_KEY = 'resend-verification-token-'
RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY = 'resend-verification-token-reversed-'
COINS_STATIC_DATA_CACHE_KEY = 'coins-static-data-cache'

orders_app_cache = PrefixedRedisCache.get_cache(prefix='orders-app-cache-')
external_exchanges_pairs_price_cache = PrefixedRedisCache.get_cache(prefix='external-exchanges-pairs-price-')
cryptocompare_pairs_price_cache = PrefixedRedisCache.get_cache(prefix='cryptocompare-pairs-price-')
facade_cache = PrefixedRedisCache.get_cache(prefix='facade-app-cache-')
last_pair_price_cache = PrefixedRedisCache.get_cache(prefix='last-pair-price-')


maxsize = settings.SETTINGS_CACHE_MAXSIZE if hasattr(
    settings, 'SETTINGS_CACHE_MAXSIZE') else 100
ttl = settings.SETTINGS_CACHE_TTL if hasattr(
    settings, 'SETTINGS_CACHE_TTL') else 60*60
settings_cache = TTLCache(maxsize, ttl)
