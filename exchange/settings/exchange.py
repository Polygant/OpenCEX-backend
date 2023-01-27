import os
from decimal import getcontext
from decimal import ROUND_DOWN

from exchange.settings import env

getcontext().rounding = ROUND_DOWN

ORDER_LIMIT = True

WITHDRAWAL_REQUEST_EXPIRATION_M = 24 * 60

INTERGRATOR_REPORTS_EMAILS = ['info@exchange.net']

STACK_EXPORT_LIMIT = 100  # limit to export stack via memcache
STACK_UPDATE_PERIOD = 1  # once a second
STACK_DOWN_TIMEOUT = 60 * 15  # 15 min
STACK_DOWN_MULTI = 3  # multiplier STACK_DOWN_TIMEOUT - etc 15,45,135

LAST_CRYPTO_WITHDRAWAL_ADDRESSES_COUNT = 3
CRYPTO_TOPUP_REQUIRED_CONFIRMATIONS_COUNT = 1

PAYOUTS_FREEZE_ON_PWD_RESET = 3 * 24 * 60  # 3 days
PAYOUTS_FREEZE_ON_2FA_RESET = 5 * 24 * 60  # 5 days

OTC_ENABLED = True
OTC_PERCENT_LIMIT = 30  # +-20%

EXCHANGE_LIMIT_PERCENTAGE = 10

PAYOUTS_PROCESSING_ENABLED = True  # Flag to disable any payouts processing

EXTERNAL_PRICES_DEVIATION_PERCENTS = 10
CRYPTOCOMPARE_DEVIATION_PERCENTS = 2

FEE_USER = env('FEE_USER', default='fee@exchange.net')

REF_BONUS = 0.5  # 50% of fee


QUARK_WAIT_SLEEP = 10
QUARK_WAIT_ATTEMPTS = 6

PLAN_TRADES_STATS_AGGRREGATION = True

# exchanges price update cache settings
PRICE_UPDATE_CACHES = {
    'otc-binance': {
        'cache_key_prefix': 'price-update-cache-otc-binance',
    }
}

ERROR_LOG_ON_AVG_TOTAL_LESS_0 = False  # avg price ounter

ORDER_DELETE_ATTEMPT_CACHE = True

CRYPTOCOMPARE_API_KEY = env('CRYPTOCOMPARE_API_KEY')

STATS_CLEANUP_MINUTE_INTERVAL_DAYS_AGO = 7  # days

EXCHANGE_DESCRIPTION = 'Exchange description'
EXCHANGE_INFO = {
    "name": "Exchange",
    "description": EXCHANGE_DESCRIPTION,
    "location": "US",
    "logo": "",
    "website": "",
    "twitter": "",
    "version": "",
    "capability": {
        "markets": True,
        "trades": True,
        "tradesByTimestamp": False,
        "tradesSocket": False,
        "orders": False,
        "ordersSocket": False,
        "ordersSnapshot": True,
        "candles": False
    }
}

PARTNER_PLATFORM_REDIRECT_LINK = ''
