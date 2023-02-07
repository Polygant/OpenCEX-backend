from django.conf.urls import url
from django.urls import path
from django.urls.conf import include
from rest_framework.routers import DefaultRouter

from core.views.inouts import BalanceView, PortfolioBalanceView, TopupRequestView, interaction, \
    interaction_dev, topup_amount, check_status_topup, withdraw_amount, BalanceByCurrencyView
from core.views.inouts import CoinsStatusView
from core.views.inouts import FeesLimitsView
from core.views.inouts import WithdrawalFeeView
from core.views.inouts import LastCryptoWithdrawalAddressesList
from core.views.inouts import TransactionsView
from core.api_urls.withdrawal import urlpatterns as withdrawal_url_patterns
from core.views.withdrawal import WithdrawalRequestView

sci_router = DefaultRouter()
sci_router.register(r'topup', TopupRequestView, basename='topup')

sci_urls = [
    path('interaction/<str:gate_name>/', interaction, name='sci_callback'),
    path('interaction_dev/<str:gate_name>/', interaction_dev, name='sci_callback_dev'),
    path('topup_amount/', topup_amount, name='topup_amount'),
    path('topup/check/status', check_status_topup, name='check_status_topup'),
    path('withdraw_amount/', withdraw_amount, name='withdraw_amount'),
]
sci_urls.extend(sci_router.urls)

router = DefaultRouter()
router.register(r'transactions', TransactionsView, basename='transaction')


urlpatterns = [
    url(r'^balance/(?P<currency>[-:\w]+)/$', BalanceByCurrencyView.as_view()),
    url(r'^balance/$', BalanceView.as_view()),
    url(r'^portfolio-balance/$', PortfolioBalanceView.as_view()),
    path(r'getlastaddresses/', LastCryptoWithdrawalAddressesList.as_view()),
    path('withdrawal/', include(withdrawal_url_patterns)),
    path(r'sci/withdrawal/', WithdrawalRequestView.as_view(actions={'post': 'create'})),  # TODO: remove. made for compatibility with frontend!
    path(r'wallet_withdrawal/', WithdrawalRequestView.as_view(actions={'post': 'create'})),  # TODO: remove. made for compatibility with frontend!
    path('sci/', include(sci_urls)),
    path(r'getcoinsstatus/', CoinsStatusView.as_view()),
    path(r'limits/', FeesLimitsView.as_view()),
    path(r'withdrawalfees/<currency>/', WithdrawalFeeView.as_view()),
]

urlpatterns.extend(router.urls)
