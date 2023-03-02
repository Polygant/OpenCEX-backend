import logging
from collections import deque

from django.conf import settings
from django.core.cache import cache
from web3 import Web3
from web3.middleware import geth_poa_middleware

from lib.notifications import send_telegram_message

BNB_PROVIDERS_CACHE = 'BNB_PROVIDERS_CACHE'
BNB_RESPONSE_TIME_COUNTER_CACHE = 'BNB_RESPONSE_TIME_COUNTER'


log = logging.getLogger(__name__)

def set_endpoints(endpoints: deque):
    cache.set(BNB_PROVIDERS_CACHE, endpoints)


def get_current_endpoint():
    endpoints = cache.get(BNB_PROVIDERS_CACHE)
    if not endpoints:
        endpoints = deque(settings.BNB_RPC_ENDPOINTS)
        set_endpoints(endpoints)
    endpoint = endpoints[0]
    return endpoint


def change_endpoint(w3_endpoint):
    current_endpoint = get_current_endpoint()
    if current_endpoint == w3_endpoint:
        endpoints = cache.get(BNB_PROVIDERS_CACHE)
        endpoints.rotate()
        set_endpoints(endpoints)
        current_endpoint = endpoints[0]
    return current_endpoint


def check_bnb_response_time(w3, time_sec):
    current_counter = cache.get(BNB_RESPONSE_TIME_COUNTER_CACHE, 0)
    if time_sec >= 2.8:
        current_counter += 1
    else:
        current_counter = 0
    # if repeated 3 times
    if current_counter >= 3:
        current_counter = 0
        w3.change_provider()
        send_telegram_message(f'Response time greater than 3s, change provider to {w3.provider.endpoint_uri}')
    cache.set(BNB_RESPONSE_TIME_COUNTER_CACHE, current_counter)


class Web3Custom(Web3):
    def __init__(self, *args, **kwargs):
        selected_provider = Web3.HTTPProvider(get_current_endpoint())
        log.info(f'Using provider {selected_provider.endpoint_uri}')
        super(Web3Custom, self).__init__(selected_provider, *args, **kwargs)

    def change_provider(self):
        provider = Web3.HTTPProvider(change_endpoint(self.provider.endpoint_uri))
        self.manager = self.RequestManager(self, provider)
        self.middleware_onion.inject(geth_poa_middleware, layer=0)
        log.info(f'Change provider to {provider.endpoint_uri}')

def get_w3_connection():
    w3 = Web3Custom()
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3
