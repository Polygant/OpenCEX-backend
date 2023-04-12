import logging

from django.contrib import admin
from django.contrib.auth import get_user_model

from admin_panel.forms import PairAdminForm
from bots.models import BotConfig
from lib.admin import BaseModelAdmin

log = logging.getLogger(__name__)

User = get_user_model()


@admin.register(BotConfig)
class BotConfigApiAdmin(BaseModelAdmin):
    fields = ('name', 'user', 'pair', 'strategy', 'match_user_orders', 'instant_match', 'ohlc_period', 'enabled',
              'loop_period', 'loop_period_random', 'min_period', 'max_period',
              'ext_price_delta', 'symbol_precision', 'quote_precision',
              'min_order_quantity', 'max_order_quantity',
              'use_custom_price', 'custom_price',
              'low_orders_match', 'low_orders_max_match_size', 'low_orders_spread_size',
              'low_orders_min_order_size', 'low_orders_match_greater_order',
              'low_spread_alert',)
    list_display = ('name', 'bot_info')
    no_delete = False
    form = PairAdminForm

    def bot_info(self, obj):
        return f'{obj.user.email}: {obj.pair.code} {obj.min_period}-{obj.max_period}s; Enabled: {obj.enabled}'

    def perform_update(self, serializer):
        serializer.save()
