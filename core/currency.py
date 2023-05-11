import decimal
from dataclasses import dataclass
from typing import Optional, Callable

from django.db import models
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.fields import Field


@dataclass(frozen=True)
class TokenParams:
    symbol: str
    contract_address: str
    decimal_places: int
    origin_energy_limit: Optional[int] = None
    consume_user_resource_percent: Optional[int] = None


@dataclass(frozen=True)
class CoinParams:
    latest_block_fn: Optional[Callable] = None
    blocks_monitoring_diff: Optional[int] = None


class CurrencyNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'currency not found'
    default_code = 'currency_not_found'


class Currency(object):
    NOT_FOUND_EXCEPTION = CurrencyNotFound

    _by_id = {}
    _by_code = {}

    @classmethod
    def get(cls, obj):
        if isinstance(obj, cls):
            return obj

        if isinstance(obj, str):
            if obj.isdigit():
                return cls._by_id[int(obj)]
            else:
                return cls._get_by_code(obj)

        if isinstance(obj, (int, decimal.Decimal)):
            return cls._by_id[int(obj)]

        raise cls.NOT_FOUND_EXCEPTION()

    @classmethod
    def exists(cls, obj):
        try:
            cls.get(obj)
            return True
        except:
            return False

    @classmethod
    def _get_by_code(cls, code):
        code = code.upper()
        if code not in cls._by_code:
            raise cls.NOT_FOUND_EXCEPTION()
        return cls._by_code[code]

    @classmethod
    def _get_by_id(cls, _id):
        _id = int(_id)
        if _id not in cls._by_id:
            raise cls.NOT_FOUND_EXCEPTION()
        return cls._by_id[_id]

    def __init__(self, id, code, is_token=False):
        self.id = id
        self.code = code.upper()
        self.is_token = is_token
        self.blockchain_list = []
        # assert id not in self.__class__._by_id
        # assert code not in self.__class__._by_code
        self.__class__._by_id[id] = self
        self.__class__._by_code[self.code] = self

    def set_blockchain_list(self, blockchain_list):
        self.blockchain_list = blockchain_list

    def __str__(self):
        return self.code

    def __repr__(self):
        return str(self)

    @property
    def CODE(self):
        return self.code

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'is_token': self.is_token,
            'blockchain_list':self.blockchain_list
        }

    def __json__(self):
        return self.to_dict()


class CurrencyModelField(models.Field):
    def db_type(self, connection):
        return 'INTEGER'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return Currency._by_id[value]

    def to_python(self, value):
        return Currency.get(value)

    def get_prep_value(self, value):
        if value is None:
            return value
        return Currency.get(value).id


class CurrencySerialField(Field):
    def to_representation(self, obj):
        return obj.code

    def to_internal_value(self, value):
        return Currency.get(value)
