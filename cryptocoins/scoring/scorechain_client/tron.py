import logging

from django.conf import settings

from .ethereum import ScorechainEthereumClient

log = logging.getLogger(__name__)


class ScorechainTronClient(ScorechainEthereumClient):
    API_URL = 'https://api.tron.scorechain.com'
    API_TOKEN = settings.SCORECHAIN_TRON_TOKEN
    BLOCKCHAIN_CURRENCY = 'TRX'

    def get_signals_list_from_data(self, data):
        return data['details']


scorechain_tron_client = ScorechainTronClient()
