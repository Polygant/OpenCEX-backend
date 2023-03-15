from django.core.cache import cache
from django.db import models

from core.consts.inouts import DISABLE_ALL
from core.consts.inouts import DISABLE_COIN_STATES
from core.consts.inouts import DISABLE_EXCHANGE
from core.consts.inouts import DISABLE_PAIRS
from core.consts.inouts import DISABLE_STACK
from core.consts.inouts import DISABLE_TOPUPS
from core.consts.inouts import DISABLE_WITHDRAWALS
from core.currency import Currency
from core.currency import CurrencyModelField

DISABLED_COINS_CACHE_KEY = 'disabled_coins_cache'


class DisabledCoin(models.Model):
    DISABLE_ALL = DISABLE_ALL
    DISABLE_COIN_STATES = DISABLE_COIN_STATES
    DISABLE_EXCHANGE = DISABLE_EXCHANGE
    DISABLE_PAIRS = DISABLE_PAIRS
    DISABLE_STACK = DISABLE_STACK
    DISABLE_TOPUPS = DISABLE_TOPUPS
    DISABLE_WITHDRAWALS = DISABLE_WITHDRAWALS

    DISABLE_LIST = (
        (DISABLE_ALL, 'Disable all'),
        (DISABLE_COIN_STATES, 'Disable coin states'),
        (DISABLE_EXCHANGE, 'Disable exchange'),
        (DISABLE_PAIRS, 'Disable pairs'),
        (DISABLE_STACK, 'Disable stack'),
        (DISABLE_TOPUPS, 'Disable topups'),
        (DISABLE_WITHDRAWALS, 'Disable withdrawals'),
    )

    currency = CurrencyModelField(unique=True)
    disable_topups = models.BooleanField(default=False)
    disable_withdrawals = models.BooleanField(default=False)
    disable_exchange = models.BooleanField(default=False)
    disable_pairs = models.BooleanField(default=False)
    disable_stack = models.BooleanField(default=False)
    disable_all = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        from core.models.facade import CoinInfo
        super(DisabledCoin, self).save(*args, **kwargs)
        self._cache_data(True)
        CoinInfo.get_coins_info(True)  # update cache

    @classmethod
    def get_coins_status(cls) -> dict:
        return cls._cache_data()

    @classmethod
    def _cache_data(cls, set_cache=False):
        data = cache.get(DISABLED_COINS_CACHE_KEY, {})
        if set_cache or not data:
            for coin in cls.objects.all():
                data[coin.currency.code] = {
                    DISABLE_TOPUPS: coin.disable_topups,
                    DISABLE_WITHDRAWALS: coin.disable_withdrawals,
                    DISABLE_EXCHANGE: coin.disable_exchange,
                    DISABLE_PAIRS: coin.disable_pairs,
                    DISABLE_STACK: coin.disable_stack,
                    DISABLE_ALL: coin.disable_all,
                }
            cache.set(DISABLED_COINS_CACHE_KEY, data)
        return data

    @classmethod
    def is_coin_disabled(cls, currency, disabled_type=None):
        if isinstance(currency, Currency):
            currency_code = currency.code
        else:
            currency_code = currency

        data = cls.get_coins_status()
        if currency_code not in data:
            return False

        res = data[currency_code][DISABLE_ALL]

        if disabled_type not in DISABLE_COIN_STATES:
            return res

        return res or data[currency_code][disabled_type]
