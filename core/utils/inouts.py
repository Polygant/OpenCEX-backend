import functools

from rest_framework.exceptions import ValidationError

from core.exceptions.inouts import BadAmount
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.fees_and_limits import FeesAndLimits


def translate_validation_errors(fn):
    """
    This hack needs because of raising exceptions in model save method
    """
    intercept_errors = (
        BadAmount,
    )

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # noinspection PyBroadException
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # if known error
            if isinstance(e, intercept_errors):
                # TODO error_format
                raise ValidationError(detail=str(e))

            # fallback
            raise

    return wrapper


def is_coin_disabled(coin_code, disabled_type):
    return DisabledCoin.is_coin_disabled(coin_code, disabled_type)


def get_withdrawal_fee(currency, blockchain_currency=None):
    if not blockchain_currency:
        blockchain_currency = currency

    return FeesAndLimits.get_fee(
        currency,
        FeesAndLimits.WITHDRAWAL,
        FeesAndLimits.ADDRESS,
        blockchain_currency,
    )


def get_min_accumulation_balance(currency):
    return FeesAndLimits.get_limit(
        currency.code,
        FeesAndLimits.ACCUMULATION,
        FeesAndLimits.MIN_VALUE
    )


def get_keeper_accumulation_balance_limit(currency):
    return FeesAndLimits.get_limit(
        currency.code,
        FeesAndLimits.ACCUMULATION,
        FeesAndLimits.KEEPER,
    )
