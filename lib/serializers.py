from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError

from core.consts.currencies import CURRENCIES_LIST
from core.currency import Currency
from core.currency import CurrencySerialField
from core.models.inouts.fees_and_limits import FeesAndLimits
from lib.fields import JSDatetimeField
from lib.helpers import to_decimal


user_field = serializers.HiddenField(default=serializers.CurrentUserDefault())


class CurrentUserEmail(serializers.CurrentUserDefault):
    def __call__(self):
        return super(CurrentUserEmail, self).__call__().email


user_email_field = serializers.HiddenField(default=CurrentUserEmail())


class CurrencyAmountLimitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(min_value=0, max_digits=32, decimal_places=8)
    currency = CurrencySerialField()

    def validate(self, data):
        data = super(CurrencyAmountLimitSerializer, self).validate(data)

        amount = data['amount']
        if amount <= 0:
            raise ValidationError({
                "message": 'amount should be greater than 0',
                "type": "bad_amount",
            })
        currency = Currency.get(data.get('currency'))

        if currency.code not in self.supported_currencies:
            raise Currency.NOT_FOUND_EXCEPTION()

        min_value = self.min_value(currency.code)
        max_value = self.max_value(currency.code)

        if min_value and amount < min_value:
            raise ValidationError({
                "message": 'Minimal amount is {}'.format(min_value),
                "type": "bad_min_amount",
                "amount": min_value
            })

        if max_value and amount > max_value:
            raise ValidationError({
                "message": 'Limit is {}'.format(max_value),
                "type": "bad_max_amount",
                "amount": max_value,
            })

        return data

    @property
    def supported_currencies(self):
        """ codes """
        return (i[1] for i in CURRENCIES_LIST)

    def min_value(self, currency_code):
        return None

    def max_value(self, currency_code):
        return None


class TopupLimitsMixIn(object):
    def min_value(self, currency_code):
        return to_decimal(FeesAndLimits.get_limit(currency_code,FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE))

    def max_value(self, currency_code):
        return to_decimal(FeesAndLimits.get_limit(currency_code, FeesAndLimits.DEPOSIT, FeesAndLimits.MAX_VALUE))


class WithdrawalLimitsMixIn(object):
    def min_value(self, currency_code):
        return to_decimal(FeesAndLimits.get_limit(currency_code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.MIN_VALUE))

    def max_value(self, currency_code):
        return to_decimal(FeesAndLimits.get_limit(currency_code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.MAX_VALUE))


class CreatedUpdatedMixIn(object):
    updated = JSDatetimeField(required=False)
    created = JSDatetimeField(required=False)


LANG_FIELD = serializers.CharField(required=False, default='en', allow_blank=True)
