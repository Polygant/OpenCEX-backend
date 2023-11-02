from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from public_api.views.common import AssetsView
from public_api.views.common import BalancesListView
from public_api.views.common import InfoView
from public_api.views.common import MarketsListView
from public_api.views.common import OrderBookView
from public_api.views.common import OrderUpdateApiView
from public_api.views.common import OrdersApiViewSet
from public_api.views.common import PairsListView
from public_api.views.common import SummaryView
from public_api.views.common import TickerView
from public_api.views.common import TradesView
from public_api.views.common import get_otc_price
from public_api.views.common import render_docs
from public_api.views.common import server_time

router = DefaultRouter(trailing_slash=False)
router.register(r'order', OrdersApiViewSet, basename='order')


urlpatterns = [
    url(r'docs$', render_docs),
    url(r'servertime$', server_time),
    url(r'assets$', AssetsView.as_view()),
    url(r'summary$', SummaryView.as_view()),
    url(r'pairs$', PairsListView.as_view()),
    url(r'trades/(?P<pair>[\w-]+)$', TradesView.as_view()),
    url(r'orderbook/(?P<pair>[\w-]+)$', OrderBookView.as_view()),
    url(r'info$', InfoView.as_view()),  # common exchange info
    url(r'markets$', MarketsListView.as_view()),  # pairs list
    url(r'ticker$', TickerView.as_view()),
    url(r'otcprice$', get_otc_price),
    # url(r'balance/(?P<currency>[\w-]+)$', BalancesListView.as_view()),  # balances by wallets (api key)
    url(r'balance$', BalancesListView.as_view()),  # balances by wallets (api key)
    url(r'order/update/', OrderUpdateApiView.as_view()),
]

urlpatterns += router.urls
