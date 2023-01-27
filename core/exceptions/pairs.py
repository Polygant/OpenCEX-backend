from lib.exceptions import BaseError


class NotFoundPair(BaseError):
    default_detail = 'Not found pair'
    default_code = 'pair_not_found'


class NotSupportedPairs(BaseError):
    default_detail = 'Not supported pair'
    default_code = 'pair_not_support'


class CoinOrPairsDisable(BaseError):
    default_detail = 'Coin or pair is not permitted to use!'
    default_code = 'coin_pair_disable'

