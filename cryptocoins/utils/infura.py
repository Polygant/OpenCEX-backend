from typing import Dict

from django.conf import settings
from web3 import Web3
from web3.providers import (
    HTTPProvider,
)


class CustomHttpProvider(HTTPProvider):
    def get_request_headers(self) -> Dict[str, str]:
        from lib.utils import get_domain
        domain = get_domain()
        return {
            'Content-Type': 'application/json',
            'User-Agent': domain,
        }


def get_web3():
    provider = CustomHttpProvider(f'https://mainnet.infura.io/v3/{settings.INFURA_API_KEY}')
    web3 = Web3(provider)
    return web3


w3 = get_web3()
