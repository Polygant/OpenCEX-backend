import logging

import requests

log = logging.getLogger(__name__)


class BtcComClient:
    def __init__(self):
        self.url = 'https://chain.api.btc.com/v3/'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}')
            res = res.json()
        except Exception as e:
            log.exception('Can\'t fetch data from btc.com')
        return res

    def get_address_info(self, address):
        uri = f'address/{address}'
        data = self._make_request(uri)['data']
        return data
