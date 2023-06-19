from rest_framework import serializers

from lib.helpers import to_decimal
from core.models.orders import ExecutionResult
from core.models.inouts.pair import PairSerialField


class PairLimitValidationSerializer(serializers.Serializer):
    ticker_id = PairSerialField(required=True)
    depth = serializers.IntegerField(min_value=0, required=False)
    type = serializers.ChoiceField(choices=['buy', 'sell', ''], required=False)


class ExecutionResultSerializer(serializers.ModelSerializer):
    trade_id = serializers.SerializerMethodField()
    base_volume = serializers.SerializerMethodField()
    target_volume = serializers.SerializerMethodField()
    trade_timestamp = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    def get_target_volume(self, obj):
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
        fields = ('trade_id', 'price', 'base_volume', 'target_volume', 'trade_timestamp', 'type')
