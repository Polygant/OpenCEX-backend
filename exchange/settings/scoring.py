from exchange.settings import env

IS_KYT_ENABLED = env('IS_KYT_ENABLED', default=False)
SCORECHAIN_BITCOIN_TOKEN = env('SCORECHAIN_BITCOIN_TOKEN')
SCORECHAIN_ETHEREUM_TOKEN = env('SCORECHAIN_ETHEREUM_TOKEN')
