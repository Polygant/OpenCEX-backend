import logging

from django.conf import settings

from .ethereum import ScorechainEthereumClient

log = logging.getLogger(__name__)

class ScorechainBnbClient(ScorechainEthereumClient):
    API_URL = 'https://api.bsc.scorechain.com'
    API_TOKEN = settings.SCORECHAIN_BNB_TOKEN
    BLOCKCHAIN_CURRENCY = 'BNB'

    def get_signals_list_from_data(self, data):
        return data['details']


scorechain_bnb_client = ScorechainBnbClient()
