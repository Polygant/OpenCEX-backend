from django.core.cache import cache
from django.db import models
from lib.helpers import to_decimal

from core.currency import CurrencyModelField, Currency

FEES_AND_LIMITS_CACHE_KEY = 'fees_and_limits_cache'


class FeesAndLimits(models.Model):

    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'
    ACCUMULATION = 'accumulation'
    ORDER = 'order'
    EXCHANGE = 'exchange'
    CODE = 'code'
    MIN_VALUE = 'min'
    MAX_VALUE = 'max'
    ADDRESS = 'address'
    VALUE = 'value'
    LIMIT_ORDER = 'limit'
    MARKET_ORDER = 'market'
    KEEPER = 'keeper'
    MAX_GAS_PRICE = 'max_gas_price'

    currency = CurrencyModelField(unique=True)
    limits_deposit_min = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_deposit_max = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_withdrawal_min = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_withdrawal_max = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_order_min = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_order_max = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_code_max = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_accumulation_min = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_keeper_accumulation_balance = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    limits_accumulation_max_gas_price = models.DecimalField(
        max_digits=32, decimal_places=8, default=0, help_text='Gwei')
    fee_deposit_address = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    fee_deposit_code = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    fee_withdrawal_code = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    fee_order_limits = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    fee_order_market = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)
    fee_exchange_value = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)

    def save(self, *args, **kwargs):
        super(FeesAndLimits, self).save(*args, **kwargs)
        self._cache_data(True)

    @classmethod
    def _cache_data(cls, set_cache=False):
        data = cache.get(FEES_AND_LIMITS_CACHE_KEY, {})
        if set_cache or not data:
            for entry in cls.objects.all():
                data[entry.currency.code] = {
                    'limits': {
                        cls.DEPOSIT: {
                            cls.MIN_VALUE: entry.limits_deposit_min,
                            cls.MAX_VALUE: entry.limits_deposit_max
                        },
                        cls.WITHDRAWAL: {
                            cls.MIN_VALUE: entry.limits_withdrawal_min,
                            cls.MAX_VALUE: entry.limits_withdrawal_max
                        },
                        cls.ORDER: {
                            cls.MIN_VALUE: entry.limits_order_min,
                            cls.MAX_VALUE: entry.limits_order_max
                        },
                        cls.CODE: {
                            cls.MAX_VALUE: entry.limits_code_max
                        },
                        cls.ACCUMULATION: {
                            cls.MIN_VALUE: entry.limits_accumulation_min,
                            cls.KEEPER: entry.limits_keeper_accumulation_balance,
                            cls.MAX_GAS_PRICE: entry.limits_accumulation_max_gas_price,
                        }
                    },
                    'fee': {
                        cls.DEPOSIT: {
                            cls.ADDRESS: entry.fee_deposit_address,
                            cls.CODE: entry.fee_deposit_code
                        },
                        cls.WITHDRAWAL: {
                            cls.ADDRESS: WithdrawalFee.get_blockchains_by_currency(entry.currency),
                            cls.CODE: entry.fee_withdrawal_code
                        },
                        cls.ORDER: {
                            cls.LIMIT_ORDER: entry.fee_order_limits,
                            cls.MARKET_ORDER: entry.fee_order_market
                        },
                        cls.EXCHANGE: {
                            cls.VALUE: entry.fee_exchange_value
                        }
                    }
                }
            cache.set(FEES_AND_LIMITS_CACHE_KEY, data)
        return data

    @classmethod
    def get_fees_and_limits(cls, refresh_cache=False):
        return cls._cache_data(refresh_cache)

    @classmethod
    def get_limit(cls, currency_code, limit_type, limit_value_type):
        data = cls.get_fees_and_limits()
        return to_decimal(data.get(currency_code, {}).get(
            'limits', {}).get(limit_type, {}).get(limit_value_type, 0))

    @classmethod
    def get_fee(cls, currency, limit_type, limit_value_type, blockchain_currency=None):
        currency_code = currency
        blockchain_currency_code = blockchain_currency

        if isinstance(currency, Currency):
            currency_code = currency.code
        if isinstance(blockchain_currency, Currency):
            blockchain_currency_code = blockchain_currency.code

        data = cls.get_fees_and_limits()
        res = data.get(currency_code, {}).get('fee', {}).get(limit_type, {}).get(limit_value_type, 0)
        if isinstance(res, dict):
            return res.get(blockchain_currency_code, 0)
        return res

    def __str__(self):
        return f'{self.currency}'


class WithdrawalFee(models.Model):
    currency = CurrencyModelField()
    blockchain_currency = CurrencyModelField()
    address_fee = models.DecimalField(
        max_digits=32, decimal_places=8, default=0)

    class Meta:
        unique_together = (('currency', 'blockchain_currency'),)

    def save(self, *args, **kwargs):
        super(WithdrawalFee, self).save(*args, **kwargs)
        FeesAndLimits.get_fees_and_limits(refresh_cache=True)

    @classmethod
    def get_blockchains_by_currency(cls, curr):
        blockchains = cls.objects.filter(currency=curr)
        return {
            blockchain.blockchain_currency.code: blockchain.address_fee for blockchain in blockchains}

