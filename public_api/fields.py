from core.consts.orders import BUY
from core.consts.orders import SELL
from rest_framework import serializers
from core.consts.orders import ORDER_CANCELED
from core.consts.orders import ORDER_CLOSED
from core.consts.orders import ORDER_OPENED

ORDER_STATUS_REVMAP = {
    ORDER_OPENED: 1,
    ORDER_CANCELED: 2,
    ORDER_CLOSED: 3
}

ORDER_STATUS_MAP = {
    1: ORDER_OPENED,
    2: ORDER_CANCELED,
    3: ORDER_CLOSED
}


class AmountField(serializers.FloatField):
    def get_attribute(self, obj):
        return obj

    def to_representation(self, obj):
        return obj.quantity_left


class OrderTypeField(serializers.Field):
    def get_attribute(self, obj):
        return obj

    def to_representation(self, obj):
        return 'sell' if obj.operation == SELL else 'buy'

    def to_internal_value(self, data):
        return SELL if data.lower() == 'sell' else BUY


class StatusField(serializers.Field):
    def get_attribute(self, obj):
        return obj

    def to_representation(self, obj):
        return ORDER_STATUS_REVMAP[obj.state]

    def to_internal_value(self, data):
        return ORDER_STATUS_MAP[int(data)]

