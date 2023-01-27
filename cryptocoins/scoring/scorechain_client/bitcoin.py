import logging

from django.conf import settings

from .base_client import ScorechainBaseClient

log = logging.getLogger(__name__)


class ScorechainBitcoinClient(ScorechainBaseClient):
    API_URL = 'https://bitcoin.scorechain.com/api'
    API_TOKEN = settings.SCORECHAIN_BITCOIN_TOKEN
    TYPE_INPUT = 'input'
    TYPE_OUTPUT = 'output'
    SIGNALS_PERCENT_KEY = 'percent'

    def fetch_address_summary(self, address: str, score_type=TYPE_INPUT, token_currency=None):
        data = self._make_request(f'/scoring/address/{score_type}/{address}')
        if 'error' not in data:
            return data
        log.warning(data)
        return None

    def get_signals_list_from_data(self, data):
        return data['details']['relationships']


scorechain_bitcoin_client = ScorechainBitcoinClient()
