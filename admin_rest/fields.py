from functools import wraps

from allauth.account.models import EmailAddress
from rest_framework import serializers
from rest_framework.fields import BooleanField
from rest_framework.relations import RelatedField

from core.consts.currencies import CURRENCIES_LIST
from core.currency import CurrencySerialField


class ForeignSerialField(RelatedField):
    """
    A read only field that represents its targets using their
    plain string representation.
    """

    def __init__(self, **kwargs):
        kwargs['read_only'] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        return {'id': value.pk, 'value': str(value)}


class CurrencySerialRestField(CurrencySerialField):
    # choices = dict(CURRENCIES_LIST)  # for OPTIONS action

    def to_representation(self, obj):
        return obj.id

    @property
    def choices(self):
        return dict(CURRENCIES_LIST)


class BooleanReadOnlyField(serializers.BooleanField):
    def __init__(self, **kwargs):
        kwargs['read_only'] = True
        super().__init__(**kwargs)


class WithdrawalSmsConfirmationField(serializers.BooleanField):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, label='SMS Confirm')

    def get_attribute(self, instance):
        return super().get_attribute(instance.profile)


def serial_field(serial_class):
    def decorator(func):
        func.serial_class = serial_class

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
