from django.core.cache import cache
from django.db import models

from core.pairs import PairModelField, Pair, PAIRS
from lib.fields import MoneyField
from django.contrib.postgres.fields import ArrayField

PAIRS_SETTINGS_CACHE_KEY = 'pairs_settings_cache'


class PairSettings(models.Model):

    PRICE_SOURCE_EXTERNAL = 1
    PRICE_SOURCE_CUSTOM = 2
    PRICE_SOURCES = (
        (PRICE_SOURCE_EXTERNAL, 'External'),
        (PRICE_SOURCE_CUSTOM, 'Custom'),
    )

    pair = PairModelField(unique=True)
    is_enabled = models.BooleanField(default=True)
    is_autoorders_enabled = models.BooleanField(default=True)
    price_source = models.SmallIntegerField(choices=PRICE_SOURCES, default=PRICE_SOURCE_EXTERNAL)
    custom_price = MoneyField(default=0.0)
    deviation = models.DecimalField(default=0.0, max_digits=5, decimal_places=4, help_text='Max order price deviation')
    enable_alerts = models.BooleanField(default=True)
    precisions = ArrayField(models.CharField(max_length=16), default=list)

    def save(self, *args, **kwargs):
        super(PairSettings, self).save(*args, **kwargs)
        self._cache_data(True)

    @classmethod
    def _cache_data(cls, set_cache=False) -> dict:
        data = cache.get(PAIRS_SETTINGS_CACHE_KEY, {})
        if set_cache or not data:
            for entry in cls.objects.all():
                data[entry.pair.code] = {
                    'is_enabled': entry.is_enabled,
                    'is_autoorders_enabled': entry.is_autoorders_enabled,
                    'price_source': entry.price_source,
                    'custom_price': entry.custom_price,
                    'deviation': entry.deviation,
                    'enable_alerts': entry.enable_alerts,
                    'precisions': entry.precisions,
                }
            cache.set(PAIRS_SETTINGS_CACHE_KEY, data)
        return data

    @classmethod
    def get_custom_price(cls, pair):
        if isinstance(pair, Pair):
            pair = pair.code
        data = cls._cache_data()
        pair_settings = data.get(pair)
        if pair_settings and pair_settings['price_source'] == cls.PRICE_SOURCE_CUSTOM:
            return pair_settings['custom_price']

    @classmethod
    def get_autoorders_enabled_pairs(cls):
        data = cls._cache_data()
        return list(pair_code for pair_code, pair_data in data.items() if pair_data['is_autoorders_enabled'])

    @classmethod
    def get_disabled_pairs(cls):
        data = cls._cache_data()
        enabled_pairs = [pair_code for pair_code, pair_data in data.items() if pair_data['is_enabled']]
        return [p.code for p in PAIRS if p.code not in enabled_pairs]

    @classmethod
    def is_pair_enabled(cls, pair):
        if isinstance(pair, Pair):
            pair = pair.code
        return cls._cache_data().get(pair, {}).get('is_enabled', False)

    @classmethod
    def get_deviation(cls, pair):
        if isinstance(pair, Pair):
            pair = pair.code
        return cls._cache_data().get(pair, {}).get('deviation', 0) * 100

    @classmethod
    def is_alerts_enabled(cls, pair):
        if isinstance(pair, Pair):
            pair = pair.code
        return cls._cache_data().get(pair, {}).get('enable_alerts')

    @classmethod
    def get_stack_precisions(cls):
        data = cls._cache_data()
        return {k: v['precisions'] for k,v in data.items()}

    @classmethod
    def get_stack_precisions_by_pair(cls, pair_code: str):
        precisions = cls.get_stack_precisions()
        return precisions.get(pair_code, [])

    def __str__(self):
        return f'{self.pair}; Enabled: {self.is_enabled}; AutoOrders: {self.is_autoorders_enabled}'
