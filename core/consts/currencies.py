from typing import List, Tuple, Union, Dict
from collections.abc import Callable

from core.currency import Currency, TokenParams, CoinParams

ALL_CURRENCIES: List[Currency] = []  # all Currency instances

CURRENCIES_LIST: List[Tuple[int, str]] = []

ERC20_CURRENCIES: Dict[Currency, TokenParams] = {}
BEP20_CURRENCIES: Dict[Currency, TokenParams] = {}
ERC20_POLYGON_CURRENCIES: Dict[Currency, TokenParams] = {}

ALL_TOKEN_CURRENCIES: List[Currency] = []

# {<Currency>: <validation_fn>} - for coins
# {<Currency>: {<Currency>: <validation_fn>}} - for tokens
CRYPTO_ADDRESS_VALIDATORS: Union[Dict[Currency, Callable], Dict[Currency, Dict[str, Callable]]] = {}

# {<Currency>: <wallet_creation_fn>} - for coins
# {<Currency>: {<Currency>: <wallet_creation_fn>}} - for tokens
CRYPTO_WALLET_CREATORS: Union[Dict[Currency, Callable], Dict[Currency, Dict[str, Callable]]] = {}

CRYPTO_COINS_PARAMS: Dict[Currency, CoinParams] = {}
