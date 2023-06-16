from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from core.serializers.orders import OrderSerializer
from django.conf import settings
from core.consts.orders import LIMIT
from core.consts.orders import EXTERNAL
from core.consts.orders import BUY
from core.models.orders import ExecutionResult
from core.models.inouts.pair import PairSerialField
from lib.fields import JSDatetimeField
from lib.helpers import to_decimal


class ApiOrderSerializer(OrderSerializer):
    def validate(self, data):
        data = super(OrderSerializer, self).validate(data)
        _type = data.get('type')
        quantity = data.get('quantity', 0) or 0
        price = data.get('price', 0) or 0

        if _type not in [LIMIT, EXTERNAL]:
            raise serializers.ValidationError("limit and OTC orders only!")

        if quantity <= 0:
            raise serializers.ValidationError('Invalid quantity.')

        if not settings.OTC_ENABLED and _type == EXTERNAL:
            raise serializers.ValidationError('OTC orders are disabled!')

        if _type == EXTERNAL:
            OTCSerializer(data=data).is_valid(raise_exception=True)
            otc_percent = data['otc_percent']
            otc_limit = data['otc_limit']
            data['price'] = self.get_otc_price(data['pair'], otc_percent)
            if data['operation'] == BUY:
                data['price'] = min([data['price'], otc_limit])
            else:
                data['price'] = max([data['price'], otc_limit])

        elif price <= 0:
            raise serializers.ValidationError('Invalid price')

        return data


class UpdateOrderSerializer(serializers.Serializer):
    # id = serializers.IntegerField(required=True)
    price = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    quantity = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)

    def validate(self, data):
        data = serializers.Serializer.validate(self, data)

        for i in ['price', 'quantity']:
            if i in data:
                break
        else:
            raise ValidationError('nothing to update!')

        if 'quantity' in data and data['quantity'] <= 0:
            raise ValidationError('quantity <= 0')
        if 'price' in data and data['price'] <= 0:
            raise ValidationError('price <= 0')
        return data


class OTCSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    otc_percent = serializers.DecimalField(
        min_value=-settings.OTC_PERCENT_LIMIT,
        max_value=+settings.OTC_PERCENT_LIMIT,
        max_digits=32, decimal_places=8,
    )
    otc_limit = serializers.DecimalField(
        min_value=0.000001,
        max_digits=32, decimal_places=8,
    )

    def validate(self, data):
        data = serializers.Serializer.validate(self, data)
        for i in ['otc_percent', 'otc_limit', 'quantity']:
            if i in data:
                break
        else:
            raise ValidationError('nothing to update!')
        if 'quantity' in data and data['quantity'] <= 0:
            raise ValidationError('quantity <= 0')
        if data['otc_limit'] <= 0:
            raise ValidationError('limit <= 0!')
        return data


class PairLimitValidationSerializer(serializers.Serializer):
    pair = PairSerialField(required=True)
    depth = serializers.IntegerField(min_value=0, required=False)


class ExecutionResultSerializer(serializers.ModelSerializer):
    trade_id = serializers.SerializerMethodField()
    base_volume = serializers.SerializerMethodField()
    quote_volume = serializers.SerializerMethodField()
    trade_timestamp = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    def get_quote_volume(self, obj):
        return to_decimal(obj.quantity) * to_decimal(obj.price)

    def get_base_volume(self, obj):
        return obj.quantity

    def get_trade_id(self, obj):
        return obj.id

    def get_trade_timestamp(self, obj):
        return int(obj.created.timestamp())

    def get_type(self, obj):
        return 'sell' if obj.matched_order.operation == 1 else 'buy'

    class Meta:
        model = ExecutionResult
        fields = ('trade_id', 'price', 'base_volume', 'quote_volume', 'trade_timestamp', 'type')
