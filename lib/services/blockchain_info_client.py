import logging

import requests

log = logging.getLogger(__name__)


class BlockchainInfoClient:
    def __init__(self):
        self.url = 'https://api.blockchain.info/haskoin-store/bch/'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}')
            res = res.json()
        except Exception as e:
            log.exception('Can\'t fetch data from btc.com')
        return res

    def get_address_info(self, address):
        uri = f'address/{address}/balance'
        data = self._make_request(uri)
        return data
