from django.db.models import CharField
from django.db.models.functions import Cast, Concat
from rest_framework import mixins, permissions, viewsets
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from core.consts.currencies import CRYPTO_WALLET_CREATORS
from core.filters.wallet import WalletHistoryFilter
from core.models.cryptocoins import UserWallet
from core.models.wallet_history import WalletHistoryItem
from core.serializers.cryptocoins import UserCurrencySerializer, UserWalletSerializer
from core.serializers.wallet_history import WalletHistoryItemSerializer


class CreateUserWallet(GenericAPIView):
    # TODO: review and rewrite!
    TIMEOUT = 30

    def post(self, request):
        serializer = UserCurrencySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = data['user']
        currency = data['currency']
        blockchain_currency = data.get('blockchain_currency')

        wallet_creator_fn = CRYPTO_WALLET_CREATORS[currency]
        if isinstance(wallet_creator_fn, dict):
            wallet_creator_fn = wallet_creator_fn[blockchain_currency.code]

        wallets = wallet_creator_fn(user_id=user.id, currency=currency)
        try:
            wallet_data = UserWalletSerializer(wallets, many=True).data
        except Exception as e:
            raise APIException(detail=str(e), code='server_error')
        return Response(status=status.HTTP_200_OK, data=wallet_data)


class UserWallets(GenericAPIView):

    def post(self, request):
        serializer = UserCurrencySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = data['user']
        currency = data.get('currency')

        # get only latest wallet for each currency
        wallets = UserWallet.objects.filter(
            user_id=user.id,
            merchant=False
        ).annotate(
            currency_str=Cast('currency', output_field=CharField()),
            blockchain_currency_str=Cast('blockchain_currency', output_field=CharField()),
            uniq_cur=Concat('currency_str', 'blockchain_currency_str')
        ).order_by('uniq_cur', '-created').distinct('uniq_cur')

        if currency:
            wallets = wallets.filter(currency=currency)
        wallet_data = UserWalletSerializer(wallets, many=True).data
        return Response(status=status.HTTP_200_OK, data=wallet_data)


class WalletHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [
        permissions.IsAuthenticated,
    ]
    serializer_class = WalletHistoryItemSerializer
    queryset = WalletHistoryItem.objects.all().select_related(
        'transaction',
    )
    filter_class = WalletHistoryFilter

    def get_queryset(self):
        return super().get_queryset().filter(
            user_id=self.request.user.id,
        )
