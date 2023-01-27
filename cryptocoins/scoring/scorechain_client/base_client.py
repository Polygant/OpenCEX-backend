import logging
from typing import Union

import requests

from cryptocoins.scoring.helpers import format_scorechain_response

log = logging.getLogger(__name__)


class ScorechainBaseClient:
    API_URL = ''
    API_TOKEN = ''
    TYPE_INPUT = ''
    TYPE_OUTPUT = ''
    SIGNALS_PERCENT_KEY = ''

    def _make_request(self, uri=''):
        res = {}
        try:
            url = f'{self.API_URL}{uri}?token={self.API_TOKEN}'
            log.info(f'Scorechain request to {url}')
            res = requests.get(url)
            res = res.json()
            log.info(f'{res }')
        except Exception as e:
            log.exception(f'Can\'t fetch data from {self.API_URL}')
        return res

    def fetch_address_summary(self, address: str, score_type=TYPE_INPUT, token_currency=None) -> Union[dict, None]:
        """
        Fetch address summary from scorechain API. Returns None if there are errors
        """
        raise NotImplementedError

    def get_signals_list_from_data(self, data):
        raise NotImplementedError

    def get_address_summary(self, address: str, score_type=TYPE_INPUT, token_currency=None) -> dict:
        data = self.fetch_address_summary(address, score_type, token_currency)

        result = {
            'address': address,
            'address_data': None,
            'riskscore': {
                'value': None
            },
        }
        if data:
            risk_value = data['scx']
            risk_formatted_signals = format_scorechain_response(
                self.get_signals_list_from_data(data),
                self.SIGNALS_PERCENT_KEY
            )

            result.update({
                'address': address,
                'address_data': data,
                'riskscore': {
                    'value': risk_value,
                    'signals': risk_formatted_signals
                }
            })
        return result
