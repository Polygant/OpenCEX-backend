from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from core.exceptions.facade import SOFSetAllFieldsRequiredError
from core.models.facade import Message
from core.models.facade import SourceOfFunds
from lib.fields import JSDatetimeField


@extend_schema_serializer(

)
class SourceOfFundsSerializer(serializers.ModelSerializer):

    def validate(self, data):
        for fieldname in self.Meta.fields:
            if fieldname not in data:
                raise SOFSetAllFieldsRequiredError()

        return data

    class Meta:
        model = SourceOfFunds
        fields = (
            'is_beneficiary',
            'profession',
            'source',
        )


class MessageSerializer(serializers.ModelSerializer):
    updated = JSDatetimeField(required=False)
    created = JSDatetimeField(required=False)

    class Meta:
        model = Message
        fields = ('id', 'subject', 'content', 'read', 'created', 'updated')
