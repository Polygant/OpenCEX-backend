from django.db.models import JSONField
from django.core.cache import cache
from django.db import models

from core.currency import CurrencyModelField
from lib.fields import MoneyField


SCORING_SETTINGS_CACHE_KEY = 'scoring_settings_cache'


class TransactionInputScore(models.Model):
    """
    Transaction with scoring, use to deny accumulation of low scoring
    inputs
    """
    SCORING_STATE_DISABLED = 1
    SCORING_STATE_SMALL_AMOUNT = 2
    SCORING_STATE_OK = 3
    SCORING_STATE_FAILED = 4

    SCORING_STATES = (
        (SCORING_STATE_DISABLED, 'Scoring disabled'),
        (SCORING_STATE_SMALL_AMOUNT, 'Amount too small'),
        (SCORING_STATE_OK, 'OK'),
        (SCORING_STATE_FAILED, 'Failed'),
    )

    created = models.DateTimeField(auto_now_add=True)
    hash = models.TextField()
    address = models.TextField()
    score = models.DecimalField(max_digits=5, decimal_places=2)
    deposit_made = models.BooleanField(default=False)
    accumulation_made = models.BooleanField(default=False)
    data = JSONField(default=dict)
    currency = CurrencyModelField(null=True, blank=True)
    token_currency = CurrencyModelField(null=True, blank=True)
    scoring_state = models.PositiveSmallIntegerField(choices=SCORING_STATES, default=SCORING_STATE_DISABLED)


class ScoringSettings(models.Model):
    """
    Scoring setup, must be single record
    """
    min_score = models.DecimalField(max_digits=5, decimal_places=2, help_text='Minimal scoring to accumulate')
    deffered_scoring_time = models.IntegerField(default=0, help_text='Time to wait scoring in minutes')
    min_tx_amount = MoneyField(default=0.001)
    currency = CurrencyModelField(db_index=True, unique=True)

    def save(self, *args, **kwargs):
        super(ScoringSettings, self).save(*args, **kwargs)
        self._cache_data(True)

    @classmethod
    def _cache_data(cls, set_cache=False):
        data = cache.get(SCORING_SETTINGS_CACHE_KEY, {})
        if set_cache or not data:
            for setting in cls.objects.all():
                data[setting.currency.code] = {
                    'min_score': setting.min_score,
                    'deffered_scoring_time': setting.deffered_scoring_time,
                    'min_tx_amount': setting.min_tx_amount,
                }
            cache.set(SCORING_SETTINGS_CACHE_KEY, data)
        return data

    @classmethod
    def get_settings(cls, currency_code: str):
        return cls._cache_data().get(currency_code)

    @classmethod
    def get_deffered_scoring_time(cls, currency_code: str):
        settings = cls.get_settings(currency_code)
        if not settings:
            return 0
        return settings['deffered_scoring_time'] * 60

    @classmethod
    def get_accumulation_min_score(cls, currency_code: str):
        settings = cls.get_settings(currency_code)
        if not settings:
            return 0
        return settings['min_score']

    @classmethod
    def need_to_check_score(cls, amount, currency_code: str):
        settings = cls.get_settings(currency_code)
        if not settings:
            return False
        return amount >= settings['min_tx_amount']
