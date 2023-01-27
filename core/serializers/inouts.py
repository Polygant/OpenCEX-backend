from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.currency import CurrencySerialField, Currency
from core.models.inouts.sci import GATES, PayGateTopup
from core.models.inouts.transaction import Transaction
from lib.serializers import user_field, TopupLimitsMixIn, CurrencyAmountLimitSerializer, CreatedUpdatedMixIn


class TransactionSerizalizer(serializers.ModelSerializer):
    currency = CurrencySerialField()

    class Meta:
        model = Transaction
        fields = ('id', 'amount', 'updated', 'created', 'currency', 'reason', 'state')


class LastCryptoWithdrawalAddressesSerializer(serializers.Serializer):
    """
    Special serializer
    """
    currency = CurrencySerialField()
    addresses = serializers.ListField(
        child=serializers.CharField(),
    )

    class Meta:
        fields = (
            'currency',
            'addresses',
        )


class TopupSerializer(serializers.ModelSerializer, TopupLimitsMixIn, CurrencyAmountLimitSerializer, CreatedUpdatedMixIn):
    user = user_field
    data = serializers.JSONField(required=False)

    class Meta:
        model = PayGateTopup
        fields = ('id', 'amount', 'updated', 'created', 'currency', 'user', 'state', 'gate_id', 'data')
        read_only_fields = ('id', 'user', 'state', 'updated', 'created')

    def validate(self, attrs):
        assert attrs['gate_id'] in GATES, ValidationError('bad gate_id')
        data = attrs.get('data', {})
        if GATES[attrs['gate_id']].NAME == 'cauri' and (data.get('cardholder') is None or data.get('cardholder') == ''):
            # TODO error_format
            raise ValidationError({'cardholder': 'This field is required.'})
        currency = Currency.get(attrs['currency'])
        if currency.id not in GATES[attrs['gate_id']].ALLOW_CURRENCY:
            # TODO error_format
            raise ValidationError({'currency': 'Incorrect currency.'})
        return super(TopupSerializer, self).validate(attrs)


class SciWithdrawalSerializerMixIn(object):
    """ only fiat and gate_id is needed """

    def validate_sci(self, attrs):
        # TODO: KYC CHECK!
        assert attrs['sci_gate_id'] in GATES, ValidationError('bad sci_gate_id')

        gate = GATES[attrs['sci_gate_id']]

        paygate_data = {'amount': attrs['amount'], 'currency': attrs['currency']}
        paygate_data.update(attrs.get('data', {}))

        gate.WITHDRAWAL_SERIALIZER(data=paygate_data).is_valid(raise_exception=True)
        return attrs
