from rest_framework import serializers

from core.models.orders import ExecutionResult
from core.models.inouts.pair import PairSerialField


class PairLimitValidationSerializer(serializers.Serializer):
    market = PairSerialField(required=True)
    limit = serializers.IntegerField(min_value=1, max_value=500, required=False)
    since = serializers.IntegerField(required=False)


class ExecutionResultSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_timestamp(self, obj):
        return obj.created.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+'Z'

    def get_amount(self, obj):
        return str(obj.quantity)

    def get_price(self, obj):
        return str(obj.price)

    class Meta:
        model = ExecutionResult
        fields = ('id', 'timestamp', 'price', 'amount')
