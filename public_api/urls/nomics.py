from django.conf.urls import url

from public_api.views.common import InfoView
from public_api.views.common import MarketsListView
from public_api.views.nomics import TradesViewNomics
from public_api.views.nomics import OrderBookView


urlpatterns = [
    url(r'info$', InfoView.as_view()),  # common exchange info
    url(r'markets$', MarketsListView.as_view()),  # pairs list
    url(r'trades$', TradesViewNomics.as_view()),  # last trades
    url(r'orders/snapshot$', OrderBookView.as_view()),  # orders snapshot
]
