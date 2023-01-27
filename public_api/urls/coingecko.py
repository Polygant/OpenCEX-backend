from django.conf.urls import url

from public_api.views.coingecko import OrderBookView
from public_api.views.coingecko import PairsListView
from public_api.views.coingecko import TickersView
from public_api.views.coingecko import TradesView
from public_api.views.coingecko import render_docs

urlpatterns = [
    url(r'pairs$', PairsListView.as_view()),
    url(r'tickers$', TickersView.as_view()),
    url(r'orderbook$', OrderBookView.as_view()),
    url(r'historical_trades$', TradesView.as_view()),
    url(r'docs$', render_docs),
]
