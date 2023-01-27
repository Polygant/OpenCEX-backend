from django.conf import settings
from rest_framework import serializers

from core.models.wallet_history import WalletHistoryItem
from lib.fields import JSDatetimeField


class WalletHistoryItemSerializer(serializers.ModelSerializer):
    confirmations_required_count = serializers.SerializerMethodField()
    confirmation_token = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    blockchain_currency = serializers.SerializerMethodField()
    data = serializers.SerializerMethodField()
    created = JSDatetimeField(required=False)
    updated = JSDatetimeField(required=False)

    def get_address(self, obj):
        addr = obj.address
        return addr

    def get_blockchain_currency(self, obj):
        blockchain = None
        if obj.operation_type == WalletHistoryItem.OPERATION_TYPE_DEPOSIT:
            wallet_transaction_object = obj.transaction.wallet_transaction.first()
            if wallet_transaction_object:
                blockchain = wallet_transaction_object.wallet.blockchain_currency.code
        if obj.operation_type == WalletHistoryItem.OPERATION_TYPE_WITHDRAWAL:
            withdrawal_request_object = obj.transaction.withdrawal_request.first()
            if withdrawal_request_object:
                blockchain = withdrawal_request_object.data.get('blockchain_currency', None)
        return blockchain

    def get_confirmations_required_count(self, obj):
        return settings.CRYPTO_TOPUP_REQUIRED_CONFIRMATIONS_COUNT

    def get_confirmation_token(self, obj: WalletHistoryItem):
        token = ''
        if obj.state == WalletHistoryItem.STATE_WAIT_CONFIRMATION and obj.operation_type == WalletHistoryItem.OPERATION_TYPE_WITHDRAWAL:
            if hasattr(obj.transaction, 'withdrawal_request'):
                wd_req = obj.transaction.withdrawal_request.first()
                if wd_req:
                    return wd_req.confirmation_token
        return token

    def get_data(self, obj: WalletHistoryItem):
        return obj.transaction.data if obj.transaction is not None else None

    class Meta:
        model = WalletHistoryItem
        fields = (
            'id',
            'created',
            'updated',
            'state',
            'operation_type',
            'currency',
            'amount',
            'tx_hash',
            'address',
            'confirmation_token',
            'confirmations_count',
            'confirmed',
            'confirmations_required_count',
            'paygate_id',
            'paygate_method',
            'blockchain_currency',
            'data',
        )
