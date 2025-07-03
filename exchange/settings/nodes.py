from exchange.settings import env

NODES_CONFIG = {
    'btc': {
        'host': env('BTC_NODE_HOST', default='localhost'),
        'port': env('BTC_NODE_PORT', default=8333),
        'username': env('BTC_NODE_USER'),
        'password': env('BTC_NODE_PASS'),
    },
    'tenz': {
        'host': env('TENZ_NODE_HOST', default='localhost'),
        'port': env('TENZ_NODE_PORT', default=8766),
        'username': env('TENZ_NODE_USER'),
        'password': env('TENZ_NODE_PASS'),
    },
}
