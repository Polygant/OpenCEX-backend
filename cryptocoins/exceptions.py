from django.utils.translation import ugettext_lazy as _
from lib.exceptions import BaseError


class CoinServiceError(BaseError):
    default_detail = _('Something went wrong.')
    default_code = 'coin_service_error'


class RetryRequired(Exception):
    """
    When something goes wrong and retry can help
    """


class UnknownToken(Exception):
    pass


class UnknownTokenSymbol(UnknownToken):

    def __init__(self, symbol: str):
        super().__init__(f'Unknown token symbol: {symbol}')


class WalletNotFound(UnknownToken):

    def __init__(self, symbol: str):
        super().__init__(f'User wallet for {symbol} not found')


class KeeperNotFound(UnknownToken):

    def __init__(self, symbol: str):
        super().__init__(f'Keeper for {symbol} not found')


class GasKeeperNotFound(UnknownToken):

    def __init__(self, symbol: str):
        super().__init__(f'Gas keeper for {symbol} not found')


class UnknownTokenAddress(UnknownToken):

    def __init__(self, address: str):
        super().__init__(f'Unknown token address: {address}')


class ScoringClientError(Exception):
    pass


class TransferAmountLowError(Exception):
    pass


class SignTxError(Exception):
    pass
