from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.currency import Currency
from core.currency import CurrencySerialField
from core.exceptions.pairs import NotFoundPair
from core.utils.facade import is_bot_user
from lib.fields import JSDatetimeField
from core.otcupdater import OtcOrdersUpdater
from core.consts.orders import EXTERNAL, STOP_LIMIT
from core.consts.orders import BUY
from core.consts.orders import LIMIT
from core.exceptions.orders import OrderPriceInvalidError, OrderQuantityInvalidError, OrderStopInvalidError, \
    OrderStopPriceInvalidError
from core.models.orders import Exchange, ExecutionResult
from core.models.orders import MARKET
from core.models.orders import EXCHANGE
from core.models.orders import Order
from core.pairs import PAIRS
from core.pairs import PairSerialField


class OTCSerializer(serializers.Serializer):
    otc_percent = serializers.DecimalField(max_digits=32, decimal_places=8)
    otc_limit = serializers.DecimalField(max_digits=32, decimal_places=8)

    def validate(self, attrs):
        attrs = serializers.Serializer.validate(self, attrs)
        if attrs['otc_percent'] < -settings.OTC_PERCENT_LIMIT:
            raise ValidationError({
                'message': f'OTC percent < {-settings.OTC_PERCENT_LIMIT}!',
                'type': 'percent_min_value'
            })
        if attrs['otc_percent'] > settings.OTC_PERCENT_LIMIT:
            raise ValidationError({
                'message': f'OTC percent > {settings.OTC_PERCENT_LIMIT}!',
                'type': 'percent_max_value'
            })
        if attrs['otc_limit'] <= 0.0000001:
            raise ValidationError({
                'message': 'limit <= 0.0000001!',
                'type': 'limit_min_value'
            })
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    pair = PairSerialField()
    user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    updated = JSDatetimeField(required=False)
    created = JSDatetimeField(required=False)
    quantity = serializers.DecimalField(max_digits=32, decimal_places=8)

    def get_otc_price(self, pair, percent):
        return OtcOrdersUpdater.make_price(pair, percent)

    def get_updated(self, obj):
        if isinstance(obj, Order):
            return int(obj.updated.timestamp() * 1000)
        else:
            return int(obj.get('updated', 0) * 1000)

    def validate(self, data):
        """
        Check that the start is before the stop.
        """
        data = super(OrderSerializer, self).validate(data)
        quantity = data.get('quantity', 0) or 0
        price = data.get('price', 0) or 0
        _type = data.get('type')

        if not settings.OTC_ENABLED and _type == EXTERNAL:
            raise serializers.ValidationError({
                'message': 'OTC orders are disabled!',
                'type': 'otc_order_disable'
            })

        if quantity <= 0:
            raise OrderQuantityInvalidError()

        if (_type in [MARKET, EXCHANGE]):
            data['price'] = None
        elif _type == EXTERNAL:
            otc_percent = data.get('otc_percent')
            otc_limit = data.get('otc_limit')
            OTCSerializer(data=data).is_valid(raise_exception=True)
            data['price'] = self.get_otc_price(data['pair'], otc_percent)
            if data['operation'] == BUY:
                data['price'] = min([data['price'], otc_limit])
            else:
                data['price'] = max([data['price'], otc_limit])
        elif _type == STOP_LIMIT:
            stop = data.get('stop')
            if stop <= 0:
                raise OrderStopInvalidError()

        elif price <= 0:
            raise OrderPriceInvalidError()

        return data

    class Meta:
        model = Order
        fields = ('id', 'user', 'state', 'pair', 'operation', 'type',
                  'quantity', 'price', 'executed', 'quantity_left', 'updated',
                  'created', 'vwap', 'otc_percent', 'otc_limit', 'stop')
        read_only_fields = ('id', 'user', 'state', 'executed', 'quantity_left', 'updated', 'created', 'vwap')


class NotifyOrderSerializer(OrderSerializer):
    class Meta(OrderSerializer.Meta):
        fields = ('id', 'state', 'pair', 'operation', 'type', 'quantity', 'price',)


class LimitOnlyOrderSerializer(OrderSerializer):
    def validate(self, data):
        if data.get('type') not in [LIMIT, EXTERNAL]:
            raise serializers.ValidationError({
                'message': "limit orders only!",
                'type': 'order_type_invalid'
            })

        user = data.get('user')
        if user and data.get('type') == EXTERNAL and not user.profile.is_auto_orders_enabled:
            raise serializers.ValidationError({
                'message': "Auto orders are disabled for user!",
                'type': 'user_auto_orders_disable'
            })

        return super(LimitOnlyOrderSerializer, self).validate(data)


class StopLimitOrderSerializer(OrderSerializer):
    def validate(self, data):
        if data.get('type') not in [STOP_LIMIT]:
            raise serializers.ValidationError("stop limit orders only!")
        return super(StopLimitOrderSerializer, self).validate(data)


class ExchangeResultSerialzier(serializers.ModelSerializer):
    base_currency = CurrencySerialField()
    quote_currency = CurrencySerialField()
    operation = serializers.IntegerField()
    order = OrderSerializer()
    cost = serializers.DecimalField(max_digits=32, decimal_places=8)
    quantity = serializers.DecimalField(max_digits=32, decimal_places=8)

    class Meta:
        model = Exchange
        fields = ('id', 'order', 'cost', 'quantity', 'operation', 'base_currency', 'quote_currency')


class ExchangeRequestSerializer(serializers.Serializer):
    operation = serializers.IntegerField(min_value=0, max_value=1)
    base_currency = CurrencySerialField()
    quote_currency = CurrencySerialField()
    quantity = serializers.DecimalField(min_value=0, max_digits=32, decimal_places=8, required=False)
    quantity_alt = serializers.DecimalField(min_value=0, max_digits=32, decimal_places=8, required=False)
    pair = PairSerialField(required=False)
    strict_pair = serializers.BooleanField(required=False)

    @classmethod
    def find_pair(cls, base, quote):
        base = Currency.get(base).code
        quote = Currency.get(quote).code

        base_quote = '{}-{}'.format(base, quote)
        quote_base = '{}-{}'.format(quote, base)

        for i in PAIRS:
            if i.code == base_quote:
                return i, True

            if i.code == quote_base:
                return i, False

        raise NotFoundPair('suitable pair not found')

    def validate(self, data):
        if data.get('quantity') is None and data.get('quantity_alt') is None:
            # TODO error_format
            raise ValidationError({
                'quantity': 'This field is required.',
                'quantity_alt': 'This field is required.',
                'message': 'Required field quantity or quantity_alt.',
            })

        data['pair'], data['strict_pair'] = self.find_pair(data['base_currency'], data['quote_currency'])
        return data


class UpdateOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    price = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    stop = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    quantity = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    otc_limit = serializers.DecimalField(min_value=0, required=False, max_digits=32, decimal_places=8)
    otc_percent = serializers.DecimalField(required=False, max_digits=32, decimal_places=8)

    def validate(self, data):
        data = serializers.Serializer.validate(self, data)

        for i in ['price', 'stop', 'quantity', 'otc_limit', 'otc_percent']:
            if i in data:
                break
        else:
            raise ValidationError({
                'message': 'nothing to update!',
                'type': 'wrong_data'
            })

        if 'quantity' in data and data['quantity'] <= 0:
            raise OrderQuantityInvalidError('quantity <= 0')
        if 'price' in data and data['price'] <= 0:
            raise OrderPriceInvalidError('price <= 0')
        if 'stop' in data and data['stop'] <= 0:
            raise OrderStopPriceInvalidError('stop <= 0')

        if 'otc_limit' in data and 'otc_percent' in data:
            OTCSerializer(data=data).is_valid(raise_exception=True)

        return data


class ExecutionResultApiSerializer(serializers.ModelSerializer):

    class Meta:
        model = ExecutionResult
        fields = (
            'id',
            'price',
            'quantity',
        )
        read_only_fields = fields


class ExecutionResultSerializer(serializers.ModelSerializer):
    pair = PairSerialField()
    operation = serializers.SerializerMethodField()
    updated = JSDatetimeField(required=False)
    created = JSDatetimeField(required=False)

    def get_operation(self, obj):
        return obj.order.operation

    class Meta:
        model = ExecutionResult
        fields = ('id', 'created', 'updated', 'operation', 'pair', 'cancelled', 'quantity', 'price')
        depth = 1


class AllOrdersSimpleSerializer(serializers.ModelSerializer):
    is_bot = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'price', 'quantity_left', 'operation', 'is_bot')

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_bot(self, obj):
        return is_bot_user(obj.user.username)
