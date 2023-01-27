from django.urls import path
from rest_framework.routers import DefaultRouter

from core.views.wallet import CreateUserWallet, UserWallets
from core.views.wallet import WalletHistoryViewSet

router = DefaultRouter()
router.register('wallet-history', WalletHistoryViewSet, basename='wallet_history_item')

urlpatterns = [
    path(r'create_new_wallet/', CreateUserWallet.as_view()),
    path(r'getwallets/', UserWallets.as_view()),
] + router.urls
