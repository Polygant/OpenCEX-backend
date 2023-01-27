from django.db import models
from django.core.cache import cache
import logging


SETTINGS_MODEL_CACHE = 'settings_model_cache'
log = logging.getLogger(__name__)


class Settings(models.Model):
    """
    Global settings from DB.
    Add file default_settings.py to root of any django module to create default settings entry in DB.
    Example default_settings.py:
        from core.consts.settings import DEFAULT_SETTINGS
        EXCHANGE_PRICE_DEVIATION = 'exchange_price_deviation'
        DEFAULT_SETTINGS[EXCHANGE_PRICE_DEVIATION] = '0.0'

        and then you can get current value from DB, using:
        current_exchange_price_deviation = Settings.get_value(EXCHANGE_PRICE_DEVIATION)
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    name = models.CharField(max_length=150, unique=True)
    value = models.CharField(max_length=150, blank=True, default='')

    def save(self, *args, **kwargs):
        super(Settings, self).save(*args, **kwargs)
        self._cache_data(True)

    @classmethod
    def _cache_data(cls, set_cache=False) -> dict:
        data = cache.get(SETTINGS_MODEL_CACHE, {})
        if set_cache or not data:
            for entry in cls.objects.all():
                data[entry.name] = entry.value
            cache.set(SETTINGS_MODEL_CACHE, data)
        return data

    @classmethod
    def get_value(cls, key):
        data = cls._cache_data()
        if key not in data:
            log.error(f'"{key}" not found in Settings')
        return data.get(key)
