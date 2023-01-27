import requests
from django.core.cache import cache
import logging

log = logging.getLogger(__name__)
BITSTAMP_MARKET_KEY = 'bitstamp_markets'


class BitstampClient:
    def __init__(self):
        self.url = 'https://www.bitstamp.net/api/'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}').json()
        except:
            log.exception('Can\'t fetch data from BitstampClient')
        return res

    def get_markets(self):
        markets = cache.get(BITSTAMP_MARKET_KEY)
        if not markets:
            markets = self._make_request('v2/trading-pairs-info/')
            markets = [m['url_symbol'] for m in markets]
            cache.set(BITSTAMP_MARKET_KEY, markets, timeout=3600*24)
        return markets

    def get_all_tickers(self):
        data = {}
        markets = self.get_markets()
        for market in markets:
            ticker_data = self._make_request(f'v2/ticker/{market}/')
            if ticker_data.get('last'):
                data[market.upper()] = ticker_data.get('last')
        return data
