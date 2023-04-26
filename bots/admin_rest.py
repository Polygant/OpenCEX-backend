import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from admin_rest import restful_admin as api_admin
from admin_rest.restful_admin import DefaultApiAdmin
from bots.models import BotConfig
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)

User = get_user_model()


@api_admin.register(BotConfig)
class BotConfigApiAdmin(DefaultApiAdmin):
    fields = ('name', 'user', 'pair', 'strategy', 'match_user_orders', 'instant_match', 'ohlc_period', 'enabled',
              'loop_period', 'loop_period_random', 'min_period', 'max_period',
              'ext_price_delta',
              'min_order_quantity', 'max_order_quantity',
              'use_custom_price', 'custom_price',
              'low_orders_match', 'low_orders_max_match_size', 'low_orders_spread_size',
              'low_orders_min_order_size', 'low_orders_match_greater_order',
              'binance_apikey', 'binance_secret', 'liquidity_buy_order_size', 'liquidity_sell_order_size',
              'liquidity_order_step', 'liquidity_min_btc_balance', 'liquidity_min_eth_balance',
              'liquidity_min_usdt_balance',
              'low_spread_alert',)
    list_display = ('name', 'bot_info')
    readonly_fields = ['binance_apikey', 'binance_secret']

    def bot_info(self, obj):
        return f'{obj.user.email}: {obj.pair.code} {obj.min_period}-{obj.max_period}s; Enabled: {obj.enabled}'

    def binance_apikey(self, obj):
        try:
            if obj.binance_api_key:
                binance_api_key = AESCoderDecoder(
                    settings.CRYPTO_KEY).decrypt(
                    obj.binance_api_key)
                return binance_api_key[:5] + '...' + binance_api_key[-5:]
        except Exception as e:
            log.exception(e)

    def binance_secret(self, obj):
        try:
            if obj.binance_secret_key:
                binance_secret_key = AESCoderDecoder(
                    settings.CRYPTO_KEY).decrypt(obj.binance_secret_key)
                return binance_secret_key[:5] + '...' + binance_secret_key[-5:]
        except Exception as e:
            log.exception(e)
