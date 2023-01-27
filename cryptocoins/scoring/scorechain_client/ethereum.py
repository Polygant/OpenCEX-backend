import enum
import logging

from django.conf import settings

from .base_client import ScorechainBaseClient
from ...utils.tokens import get_token_contract_address

log = logging.getLogger(__name__)


class ScoreType(enum.Enum):
    INPUT = 'incoming'
    OUTPUT = 'outgoing'


class ScorechainEthereumClient(ScorechainBaseClient):
    API_URL = 'https://api.ethereum.scorechain.com'
    API_TOKEN = settings.SCORECHAIN_ETHEREUM_TOKEN
    TYPE_INPUT = 'incoming'
    TYPE_OUTPUT = 'outgoing'
    SIGNALS_PERCENT_KEY = 'percentage'
    BLOCKCHAIN_CURRENCY = 'ETH'

    def fetch_address_summary(self, address: str, score_type=TYPE_INPUT, token_currency=None):
        if token_currency:
            token_addr = get_token_contract_address(token_currency, self.BLOCKCHAIN_CURRENCY)
            data = self._make_request(f'/scoring/address/{address}/coin/{token_addr}/{score_type}')
        else:
            data = self._make_request(f'/scoring/address/{address}/{score_type}')
        if data['success']:
            return data['result']
        log.warning(data)
        return None

    def get_signals_list_from_data(self, data):
        return data['details']


scorechain_ethereum_client = ScorechainEthereumClient()
