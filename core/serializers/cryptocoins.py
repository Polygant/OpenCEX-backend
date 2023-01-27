from django.conf import settings
from rest_framework import serializers

from core.currency import CurrencySerialField
from core.models.cryptocoins import UserWallet


class UserCurrencySerializer(serializers.Serializer):
    """
    Used when create new user wallet and requesting wallets list
    """
    currency = CurrencySerialField(required=False)
    blockchain_currency = CurrencySerialField(required=False)
    user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )


class UserWalletSerializer(serializers.ModelSerializer):
    currency = CurrencySerialField()
    blockchain_currency = CurrencySerialField()

    class Meta:
        model = UserWallet
        fields = (
            'currency',
            'blockchain_currency',
            'address',
            'merchant',
            'block_type',
        )
