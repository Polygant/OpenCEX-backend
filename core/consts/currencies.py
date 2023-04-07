from dataclasses import dataclass
from typing import List, Tuple, Union, Dict, Optional
from collections.abc import Callable

from core.currency import Currency, TokenParams, CoinParams


@dataclass
class BlockchainAccount:
    """
    Blockchain Account Info
    """
    address: str
    private_key: str
    public_key: Optional[str] = None
    redeem_script: Optional[str] = None


ALL_CURRENCIES: List[Currency] = []  # all Currency instances

CURRENCIES_LIST: List[Tuple[int, str]] = []

ERC20_CURRENCIES: Dict[Currency, TokenParams] = {}
TRC20_CURRENCIES: Dict[Currency, TokenParams] = {}
BEP20_CURRENCIES: Dict[Currency, TokenParams] = {}
ERC20_POLYGON_CURRENCIES: Dict[Currency, TokenParams] = {}

ALL_TOKEN_CURRENCIES: List[Currency] = []

# {<Currency>: <validation_fn>} - for coins
# {<Currency>: {<Currency>: <validation_fn>}} - for tokens
CRYPTO_ADDRESS_VALIDATORS: Union[
    Dict[Currency, Callable],
    Dict[Currency, Dict[str, Callable]],
    dict
] = {}

# {<Currency>: <wallet_creation_fn>} - for coins
# {<Currency>: {<Currency>: <wallet_creation_fn>}} - for tokens
CRYPTO_WALLET_CREATORS: Union[
    Dict[Currency, Callable],
    Dict[Currency, Dict[str, Callable]],
    dict
] = {}

CRYPTO_COINS_PARAMS: Dict[Currency, CoinParams] = {}

CRYPTO_WALLET_ACCOUNT_CREATORS: Dict[Currency, BlockchainAccount] = {}
