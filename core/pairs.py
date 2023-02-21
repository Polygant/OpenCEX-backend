from django.db import models
from rest_framework.fields import Field

from core.currency import Currency
from core.currency import CurrencyNotFound
from core.consts.pairs import *


PAIRS = []


PAIRS_LIST = [
    (BTC_USDT, 'BTC-USDT', ['100', '10', '1', '0.1', '0.01']),
    (ETH_USDT, 'ETH-USDT', ['100', '10', '1', '0.1', '0.01']),
    (TRX_USDT, 'TRX-USDT', ['0.01', '0.001', '0.0001', '0.00001']),
    (BNB_USDT, 'BNB-USDT', ['100', '10', '1', '0.1', '0.01']),
]

pairs_ids_values = [(p[0], p[1]) for p in PAIRS_LIST]


class PairNotFound(CurrencyNotFound):
    default_detail = 'pair not found'


class Pair(Currency):
    NOT_FOUND_EXCEPTION = PairNotFound

    _by_id = {}
    _by_code = {}

    def __init__(self, id, code, precisions):
        base, quote = code.split('-')
        self.base = Currency.get(base)
        self.quote = Currency.get(quote)
        self.stack_precisions = precisions
        Currency.__init__(self, id, code)
        self.add_to_global_list()

    def add_to_global_list(self):
        global PAIRS
        PAIRS.append(self)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'base': self.base.to_dict(),
            'quote': self.quote.to_dict(),
            'stack_precisions': self.stack_precisions
        }

    def __json__(self):
        return self.to_dict()


for _id, code, precisions in PAIRS_LIST:
    _ = Pair(_id, code, precisions)


class PairModelField(models.Field):

    def __init__(self, *args, **kwargs):
        # kwargs['choices'] = [(p[1], p[1]) for p in PAIRS_LIST]
        super().__init__(*args, **kwargs)

    def db_type(self, connection):
        return 'INTEGER'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return Pair.get(value)

    def to_python(self, value):
        return Pair.get(value)

    def get_prep_value(self, value):
        return Pair.get(value).id


class PairSerialField(Field):
    def to_representation(self, obj):
        return obj.code

    def to_internal_value(self, value):
        return Pair.get(value)


class PairSerialRestField(PairSerialField):
    choices = dict([(p[0], p[1]) for p in PAIRS_LIST])  # for OPTIONS action

    def to_representation(self, obj):
        return obj.id
