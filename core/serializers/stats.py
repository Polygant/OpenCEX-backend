from rest_framework import serializers

from core.models.inouts.pair import PairSerialField
from lib.fields import JSDatetimeField


class StatsSerializer(serializers.Serializer):
    start_ts = JSDatetimeField()
    stop_ts = JSDatetimeField()
    pair = PairSerialField()
    frame = serializers.ChoiceField(
        choices=(
            ('minute', 'minute'),
            ('hour', 'hour'),
            ('day', 'day')
        )
    )
