import os

from django.utils import timezone

from exchange.settings import env

CRYPTO_TESTNET = False
FORCE_WALLET_ADDRESS_GENERATE = False

BTC_SAFE_ADDR = env('BTC_SAFE_ADDR')

ETH_SAFE_ADDR = env('ETH_SAFE_ADDR')

BNB_SAFE_ADDR = env('BNB_SAFE_ADDR')

TRX_SAFE_ADDR = env('TRX_SAFE_ADDR')

MATIC_SAFE_ADDR = env('MATIC_SAFE_ADDR')


BTC_BLOCK_GENERATION_TIME = 5 * 60.0
BTC_NODE_CONNECTION_RETRIES = 5
SAT_PER_BYTES_UPDATE_PERIOD = 120  # 2min
SAT_PER_BYTES_MIN_LIMIT = 3
SAT_PER_BYTES_MAX_LIMIT = 60
SAT_PER_BYTES_RATIO = 1


# Ethereum & ERC
WEB3_INFURA_API_KEY = env('INFURA_API_KEY', default='')
WEB3_INFURA_API_SECRET = env('INFURA_API_SECRET', default='')
ETH_CHAIN_ID = 1  # 3 for Ropsten
ETH_TX_GAS = 21000
ETH_BLOCK_GENERATION_TIME = 15.0
ETH_ERC20_ACCUMULATION_PERIOD = 60.0
ETH_GAS_PRICE_UPDATE_PERIOD = 30
ETH_GAS_PRICE_COEFFICIENT = 0.1
ETH_MAX_GAS_PRICE = 200000000000  # wei
ETH_MIN_GAS_PRICE = 20000000000  # wei

BNB_CHAIN_ID = 56
BNB_TX_GAS = 21000
BNB_BEP20_ACCUMULATION_PERIOD = 60
BNB_BLOCK_GENERATION_TIME = 15
BNB_GAS_PRICE_UPDATE_PERIOD = 60
BNB_GAS_PRICE_COEFFICIENT = 0.1
BNB_MAX_GAS_PRICE = 300000000000
BNB_MIN_GAS_PRICE = 5000000000
BNB_RPC_ENDPOINTS = [
    'https://bsc-dataseed.binance.org/',
    'https://bsc-dataseed1.defibit.io/',
    'https://bsc-dataseed1.ninicoin.io/',
    'https://bsc-dataseed1.binance.org/',
    'https://bsc-dataseed2.binance.org/',
    'https://bsc-dataseed3.binance.org/',
    'https://bsc-dataseed4.binance.org/',
    'https://bsc-dataseed1.defibit.io/',
    'https://bsc-dataseed2.defibit.io/',
    'https://bsc-dataseed3.defibit.io/',
    'https://bsc-dataseed4.defibit.io/',
    'https://bsc-dataseed1.ninicoin.io/',
    'https://bsc-dataseed2.ninicoin.io/',
    'https://bsc-dataseed3.ninicoin.io/',
    'https://bsc-dataseed4.ninicoin.io/',
    'https://bsc-dataseed1.bnbchain.org',
    'https://bsc-rpc.gateway.pokt.network',
    'https://bscrpc.com',
    'https://bsc.publicnode.com',
]

TRX_NET_FEE = env('TRX_NET_FEE', default=3_000_000)  # 3 TRX
TRC20_FEE_LIMIT = env('TRC20_FEE_LIMIT', default=30_000_000)  # 30 TRX
TRX_BLOCK_GENERATION_TIME = env('TRX_BLOCK_GENERATION_TIME', default=3)
TRX_TRC20_ACCUMULATION_PERIOD = env('TRX_TRC20_ACCUMULATION_PERIOD', default=1 * 60.0)
TRC20_ENERGY_UNIT_PRICE = 420
TRC20_FEE_LIMIT_FACTOR = 1.1
RECEIPT_RETRY_INTERVAL = 5
RECEIPT_RETRY_ATTEMPTS = 3

MATIC_CHAIN_ID = 137
MATIC_TX_GAS = 21000
MATIC_ACCUMULATION_PERIOD = 60
MATIC_BLOCK_GENERATION_TIME = 15
MATIC_GAS_PRICE_UPDATE_PERIOD = 60
MATIC_GAS_PRICE_COEFFICIENT = 0.1
MATIC_MAX_GAS_PRICE = 300000000000
MATIC_MIN_GAS_PRICE = 5000000000

TRONGRID_API_KEY = [env('TRONGRID_API_KEY', default='')]
ETHERSCAN_KEY = env('ETHERSCAN_KEY', default='')
BSCSCAN_KEY = env('BSCSCAN_KEY', default='')
POLYGONSCAN_KEY = env('POLYGONSCAN_KEY', default='')

LATEST_ADDRESSES_REGENERATION = timezone.datetime(2021, 1, 28, 11, 20)

CRYPTO_KEY_OLD = env('CRYPTO_KEY_OLD', default='')
CRYPTO_KEY = env('CRYPTO_KEY', default='')

INFURA_API_KEY = env('INFURA_API_KEY', default='')
INFURA_API_SECRET = env('WEB3_INFURA_API_SECRET', default='')

MIN_COST_ORDER_CANCEL = 0.0000001
