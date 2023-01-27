from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from core.views.orders import ExchangeView, StopLimitView, AllOrdersView, LatestCandleView
from core.views.orders import LastExecutedOrdersView
from core.views.orders import LastTradesView
from core.views.orders import MarketView
from core.views.orders import OrdersView
from core.views.orders import OrderUpdateView
from core.views.orders import PairsListView
from core.views.orders import PairsVolumeView
from core.views.orders import StackView
from core.views.orders import ExchangeEmailView


router = DefaultRouter()
router.register(r'orders', OrdersView, basename='order')


urlpatterns = [
    url(r'pairs/?$', PairsListView.as_view()),
    url(r'stack/(?P<pair>[a-zA-Z-]+)/$', StackView.as_view()),
    url(r'market/$', MarketView.as_view()),
    url(r'exchange/$', ExchangeView.as_view()),
    url(r'stop-limit/$', StopLimitView.as_view()),
    url(r'last_executed_orders/$', LastExecutedOrdersView.as_view({'get': 'list'})),
    url(r'pairs_volume/$', PairsVolumeView.as_view()),
    url(r'recent_trades/$', LastTradesView.as_view({'get': 'list'})),
    url(r'order_update/$', OrderUpdateView.as_view()),
    url(r'exchange/send_email/$', ExchangeEmailView.as_view()),
    url(r'allorders/$', AllOrdersView.as_view()),
    url(r'latest_candle/$', LatestCandleView.as_view()),
]

urlpatterns.extend(router.urls)
