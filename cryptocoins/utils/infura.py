from typing import Dict

from web3 import Web3
from web3.auto.infura.endpoints import (
    INFURA_MAINNET_DOMAIN,
    build_http_headers,
    build_infura_url,
)
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
    provider = CustomHttpProvider(build_infura_url(INFURA_MAINNET_DOMAIN), build_http_headers())
    web3 = Web3(provider)
    return web3


w3 = get_web3()
