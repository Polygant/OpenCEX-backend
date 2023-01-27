import datetime
import logging

import pytz
import requests

from lib.helpers import to_decimal

log = logging.getLogger(__name__)

SUPPORTED_COINS = ['btc', 'ltc', 'dash', 'doge', 'bcy']


class BlockcypherClient:
    BTC = 'btc'

    def __init__(self, currency=BTC):
        if currency not in SUPPORTED_COINS:
            raise Exception(f'Only {SUPPORTED_COINS} supported')
        self.url = f'https://api.blockcypher.com/v1/{currency}/main/'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}?limit=2000')
            res = res.json()
        except Exception as e:
            log.exception('Can\'t fetch data from blockcypher')
        return res

    def get_transactions(self, address):
        uri = f'addrs/{address}'
        txs = self._make_request(uri)

        all_txs = list([{
            'confirmed': pytz.UTC.localize(datetime.datetime.strptime(t['confirmed'],'%Y-%m-%dT%H:%M:%SZ')),
            'hash': t['tx_hash'],
            'spent': t.get('spent', True),
            'ref_balance': to_decimal(t['ref_balance'] / 10**8),
            'value': to_decimal(t['value'] / 10**8)
        } for t in txs['txrefs']])
        return all_txs[::-1]
