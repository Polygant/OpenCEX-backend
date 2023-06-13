from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from lib.fields import MoneyField
from core.models.inouts.pair import Pair, PairModelField
from lib.cipher import AESCoderDecoder
from django.conf import settings


User = get_user_model()


class BotConfig(models.Model):
    TRADE_STRATEGY_DRAW = 'trade_draw_graph'

    TRADE_STRATEGIES = (
        (TRADE_STRATEGY_DRAW, 'Draw graph'),
    )

    name = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    pair = models.ForeignKey(Pair, on_delete=models.CASCADE)
    strategy = models.CharField(choices=TRADE_STRATEGIES, max_length=255, default=TRADE_STRATEGY_DRAW)

    symbol_precision = models.IntegerField(default=4)
    quote_precision = models.IntegerField(default=4)

    loop_period = models.IntegerField(default=10)
    loop_period_random = models.BooleanField(default=False)
    min_period = models.PositiveSmallIntegerField(verbose_name='Min period in seconds', default=30, validators=[
        MinValueValidator(5),
    ])
    max_period = models.PositiveSmallIntegerField(verbose_name='Max period in seconds', default=60, validators=[
        MinValueValidator(5),
    ])
    ext_price_delta = MoneyField(default=0.001)
    min_order_quantity = MoneyField(default=0.1)
    max_order_quantity = MoneyField(default=0.5)
    enabled = models.BooleanField(default=True)
    stopped = models.BooleanField(default=False)
    match_user_orders = models.BooleanField(default=False)
    next_launch = models.DateTimeField(blank=True)
    instant_match = models.BooleanField(default=False)
    use_custom_price = models.BooleanField(default=False)
    custom_price = MoneyField(default=0)

    is_ohlc_price_used = models.BooleanField(default=False)
    ohlc_period = models.IntegerField(default=60, help_text='minutes')

    low_orders_match = models.BooleanField(default=False)
    low_orders_max_match_size = models.FloatField(default=1.0)
    low_orders_spread_size = models.FloatField(default=1.0)
    low_orders_min_order_size = models.FloatField(default=1.0)
    low_orders_match_greater_order = models.BooleanField(default=False)

    low_spread_alert = models.BooleanField(default=False)
    cancel_order_error = models.BooleanField(default=False)
    create_order_error = models.BooleanField(default=False)
    authorization_error = models.BooleanField(default=False)

    ohlc_range_from = models.FloatField(default=1.0)
    ohlc_range_to = models.FloatField(default=1.0)
    ohlc_step = models.FloatField(default=1.0)
    ohlc_HL_delta = models.FloatField(default=1.0)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self.next_launch:
            self.next_launch = timezone.now()
        super().save(force_insert, force_update, using, update_fields)

    def encrypt_keys(self):
        self.binance_api_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(self.binance_api_key)
        self.binance_secret_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(self.binance_secret_key)
        self.save()

    def __str__(self):
        return f'{self.name} - {self.user.username}: {self.pair} {self.min_period}-{self.max_period}s (Enabled: {self.enabled})'

    class Meta:
        indexes = [
            models.Index(fields=[
                'enabled',
                'next_launch',
            ]),
        ]


class OrderMatch(models.Model):
    SIDE_BUY = 1
    SIDE_SELL = 2

    SIDES = (
        (SIDE_BUY, 'Buy'),
        (SIDE_SELL, 'Sell'),
    )

    created = models.DateTimeField(auto_now_add=True)
    pair = PairModelField(Pair, on_delete=models.CASCADE)
    quantity = MoneyField()
    price = MoneyField()
    side = models.PositiveSmallIntegerField(default=SIDE_BUY, choices=SIDES)


class OrderMatchStat(models.Model):
    created = models.DateTimeField(default=timezone.now)
    deals = models.PositiveIntegerField(default=0)
    pair = PairModelField(Pair, on_delete=models.CASCADE)
    total_buy = MoneyField()
    total_sell = MoneyField()
    change = MoneyField()

