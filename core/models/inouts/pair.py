from rest_framework.fields import Field

import decimal

from django.db import models
from django.db.models import UniqueConstraint

from core.consts.pairs import *
from core.currency import CurrencyModelField, CurrencyNotFound

PAIRS_LIST = [
    (BTC_USDT, 'BTC-USDT'),
    (ETH_USDT, 'ETH-USDT'),
    (TRX_USDT, 'TRX-USDT'),
    (BNB_USDT, 'BNB-USDT'),
]

class PairNotFound(CurrencyNotFound):
    default_detail = 'pair not found'


class Pair(models.Model):
    id = models.AutoField(primary_key=True)
    base = CurrencyModelField()
    quote = CurrencyModelField()

    @property
    def code(self):
        return f'{self.base}-{self.quote}'

    def to_dict(self):
        return {
            'id': self.id,
            'code': f'{self.base.code}-{self.quote.code}',
            'base': self.base.to_dict(),
            'quote': self.quote.to_dict(),
        }

    @classmethod
    def get(cls, obj):
        if isinstance(obj, cls):
            return obj

        try:
            if isinstance(obj, str):
                if obj.isdigit():
                    return cls.objects.get(id=int(obj))
                else:
                    base, quote = obj.upper().split('-')
                    return cls.objects.get(base=base, quote=quote)

            if isinstance(obj, (int, decimal.Decimal)):
                return cls.objects.get(id=int(obj))
        except Pair.DoesNotExist:
            raise PairNotFound()

        raise PairNotFound()

    @classmethod
    def exists(cls, obj):
        try:
            cls.get(obj)
            return True
        except:
            return False

    def _get_by_code(self, code):
        base, quote = code.upper().split('-')
        try:
            return self.objects.get(base=base, quote=quote)
        except Pair.DoesNotExist:
            raise PairNotFound()

    def _get_by_id(self, _id):
        _id = int(_id)
        try:
            return self.objects.get(id=id)
        except Pair.DoesNotExist:
            raise PairNotFound()

    def __str__(self):
        return self.code

    def __repr__(self):
        return str(self)

    def __json__(self):
        return self.to_dict()

    class Meta:
        UniqueConstraint(fields=['base', 'quote'], name='unique_base_quote')


class PairSerialField(Field):
    def to_representation(self, obj):
        return f'{obj.base}-{obj.quote}'.upper()

    def to_internal_value(self, value):
        return Pair.get(value)


class PairSerialRestField(PairSerialField):
    def to_representation(self, obj):
        return obj.id

    @property
    def choices(self):
        """for OPTIONS action"""
        return {pair.id: pair.code for pair in Pair.objects.all()}


class PairModelField(models.ForeignKey):
    pass
