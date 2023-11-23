from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.consts.inouts import DISABLE_WITHDRAWALS
from core.consts.currencies import CRYPTO_ADDRESS_VALIDATORS
from core.currency import Currency
from core.models.inouts.withdrawal import WithdrawalRequest, WithdrawalUserLimit
from core.serializers.inouts import SciWithdrawalSerializerMixIn
from core.utils.inouts import is_coin_disabled
from lib.serializers import CreatedUpdatedMixIn
from lib.serializers import CurrencyAmountLimitSerializer
from lib.serializers import WithdrawalLimitsMixIn
from lib.serializers import user_field
from lib.services.twilio import TwilioClient
from lib.services.twilio import twilio_client


class BaseWithdrawalSerializer(serializers.ModelSerializer, CreatedUpdatedMixIn, WithdrawalLimitsMixIn, CurrencyAmountLimitSerializer):
    user = user_field
    data = serializers.JSONField(required=False)
    sci_gate_id = serializers.IntegerField(required=False)

    class Meta:
        model = WithdrawalRequest
        fields = ('id', 'amount', 'updated', 'created', 'currency', 'user', 'state', 'sci_gate_id', 'data')
        read_only_fields = ('id', 'user', 'state', 'updated', 'created')


class CryptoWithdrawalSerializerMixIn(object):
    CHECKERS = CRYPTO_ADDRESS_VALIDATORS

    @classmethod
    def check(cls, currency, addr, blockchain_currency=None):
        validator = cls.CHECKERS[currency]
        if isinstance(validator, dict):
            if not blockchain_currency:
                # TODO error_format
                raise ValidationError({
                    'message': 'blockchain_currency not provided',
                    'type': 'field_required'
                })
            # validate
            Currency.get(blockchain_currency)
            return validator[blockchain_currency](addr)
        return validator(addr)

    def validate_crypto(self, attrs):
        currency = attrs['currency']
        if currency not in self.CHECKERS:
            """ checker is a must """
            raise Currency.NOT_FOUND_EXCEPTION('not supported currency')

        if not attrs.get('data'):
            # TODO error_format
            raise ValidationError('no withdrawal data provided!')

        addr = attrs['data'].get('destination')
        blockchain_currency = attrs['data'].get('blockchain_currency')
        if not addr:
            # TODO error_format
            raise ValidationError('no destination data provided!')

        if not self.check(currency, addr, blockchain_currency):
            raise ValidationError({
                'message': 'bad addr!',
                'type': 'invalid_address'
            })

        return attrs


class WithdrawalSerializer(CryptoWithdrawalSerializerMixIn, SciWithdrawalSerializerMixIn, BaseWithdrawalSerializer):
    destination = serializers.CharField(required=False)  # for compatibility
    gate_id = serializers.IntegerField(required=False)  # for compatibility
    sms_code = serializers.CharField(required=False)
    blockchain_currency = serializers.CharField(required=False)
    # TODO: remove after front update

    class Meta(BaseWithdrawalSerializer.Meta):
        fields = list(BaseWithdrawalSerializer.Meta.fields) + \
                 ['destination', 'gate_id', 'sms_code', 'blockchain_currency']
        read_only_fields = list(BaseWithdrawalSerializer.Meta.read_only_fields)

    def validate(self, attrs):
        sms_code = attrs.pop('sms_code', None)
        attrs = BaseWithdrawalSerializer.validate(self, attrs)
        if is_coin_disabled(attrs['currency'].code, DISABLE_WITHDRAWALS):
            raise ValidationError({
                'message': f'InOuts for {attrs["currency"].code} disabled!',
                'type': 'inouts_disable',
                'currency': attrs["currency"].code
            })

        if attrs['user'].restrictions.disable_withdrawals:
            raise ValidationError({
                'message': f'Withdrawal creation is restricted',
                'type': 'user_disable_withdrawals'
            })

        self.check_verification_code(attrs['user'], sms_code)

        # compatibility with previous version!
        sci_gate_id = attrs.get('sci_gate_id') or attrs.pop('gate_id', None)

        limit_data = WithdrawalUserLimit.get_limits(attrs['user'])
        user_limit = limit_data.get('limit')
        amount = attrs['amount']
        if attrs['currency'] != Currency.get('USDT'):
            from core.cache import external_exchanges_pairs_price_cache
            price = external_exchanges_pairs_price_cache.get('{}-{}'.format(attrs['currency'].code, 'USDT'), 1)
            amount = amount * price

        if limit_data.get('amount', 0) + amount > user_limit.amount:
            raise ValidationError({
                'message': 'Out of limit!',
                'type': 'out_of_limit'
            })

        if sci_gate_id:
            attrs['sci_gate_id'] = sci_gate_id
            attrs = self.validate_sci(attrs)
        else:
            destination = attrs.get('data', {}).get('destination') or attrs.pop('destination', None)
            blockchain_currency = attrs.get('data', {}).get('blockchain_currency') \
                                  or attrs.pop('blockchain_currency', None)
            if not destination:
                raise ValidationError('destination required!')

            attrs['data'] = attrs.get('data', {})
            attrs['data']['destination'] = destination
            attrs['data']['blockchain_currency'] = blockchain_currency

            attrs = self.validate_crypto(attrs)
        return attrs

    def check_verification_code(self, user, code):
        if not settings.IS_SMS_ENABLED:
            return
        if not user.profile.withdrawals_sms_confirmation:
            return

        if not user.profile.phone:
            raise ValidationError({
                'message': f'Phone number is not set',
                'type': 'user_phone_not_set'
            })

        if not code or not twilio_client.check_code(user.profile.phone, code, TwilioClient.TYPE_WITHDRAWAL):
            raise ValidationError({
                'message': f'Incorrect code!',
                'type': 'code_incorrect'
            })


class ConfirmationTokenSerializer(serializers.Serializer):
    confirmation_token = serializers.CharField(max_length=6, min_length=6)


class ResendWithdrawalRequestConfirmationEmailSerializer(serializers.Serializer):
    confirmation_token = serializers.CharField(max_length=6, min_length=6, required=False)
    withdrawal_request_id = serializers.IntegerField(required=False)


class CancelWithdrawalRequestEmailSerializer(serializers.Serializer):
    confirmation_token = serializers.CharField(max_length=6, min_length=6, required=False)
    withdrawal_request_id = serializers.IntegerField(required=False)
