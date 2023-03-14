import logging
import time
from decimal import Decimal
from typing import Union, List, Dict, Type, Optional

import cachetools.func
from web3 import Web3

from core.currency import TokenParams, Currency
from core.models import FeesAndLimits, UserWallet
from cryptocoins.exceptions import UnknownTokenSymbol, UnknownTokenAddress
from cryptocoins.utils.commons import get_user_addresses, BlockchainAccount, get_keeper_wallet, get_user_wallet
from cryptocoins.utils.helpers import get_amount_from_base_denomination
from cryptocoins.utils.helpers import get_base_denomination_from_amount

log = logging.getLogger(__name__)


class BlockchainTransaction:
    """Simple tx representation"""
    def __init__(self, tx_data: dict):
        self.hash = tx_data['hash']
        self.from_addr = tx_data['from_addr']
        self.to_addr = tx_data['to_addr']
        self.value = tx_data['value']
        self.contract_address = tx_data['contract_address']
        self.is_success = tx_data.get('is_success') or True

    def as_dict(self) -> dict:
        return {
            'hash': self.hash,
            'from_addr': self.from_addr,
            'to_addr': self.to_addr,
            'value': self.value,
            'contract_address': self.contract_address,
        }

    @classmethod
    def from_node(cls, node_tx_data):
        raise NotImplementedError


class Token:
    ABI = None
    BLOCKCHAIN_CURRENCY: Currency = None
    DEFAULT_TRANSFER_GAS_LIMIT: int = None
    DEFAULT_TRANSFER_GAS_MULTIPLIER: int = None
    CHAIN_ID: int = None

    def __init__(self, client, token_params: TokenParams, manager):
        self.client = client
        self.params = token_params
        self.currency = Currency.get(self.params.symbol)
        self.contract = self.get_contract()
        self.manager = manager
        log.info(f'Token registered: {self.params.symbol} {self.params.contract_address}')

    def decode_function_input(self, data: Union[str, bytes]):
        raise NotImplementedError

    def get_contract(self):
        raise NotImplementedError

    def send_token(self, private_key, to_address, amount, **kwargs):
        raise NotImplementedError

    def get_base_denomination_from_amount(self, amount: Decimal) -> int:
        """Get amount in base denomination"""
        return get_base_denomination_from_amount(amount, self.params.decimal_places)

    def get_amount_from_base_denomination(self, amount) -> Decimal:
        """Get amount from base denomination"""
        return get_amount_from_base_denomination(amount, self.params.decimal_places)

    @property
    def withdrawal_min_amount(self):
        return FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.MIN_VALUE)

    @property
    def deposit_min_amount(self):
        return FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE)

    @property
    def withdrawal_fee(self):
        return FeesAndLimits.get_fee(
            self.currency.code,
            FeesAndLimits.WITHDRAWAL,
            FeesAndLimits.ADDRESS,
            self.BLOCKCHAIN_CURRENCY
        )

    @property
    def accumulation_min_balance(self):
        return FeesAndLimits.get_limit(
            self.currency.code,
            FeesAndLimits.ACCUMULATION,
            FeesAndLimits.MIN_VALUE
        )

    @property
    def keeper_accumulation_balance_limit(self):
        return FeesAndLimits.get_limit(
            self.currency.code,
            FeesAndLimits.ACCUMULATION,
            FeesAndLimits.KEEPER
        )

    def get_base_denomination_balance(self, address: str) -> int:
        return self.contract.functions.balanceOf(address).call()

    def get_balance(self, address: str) -> Decimal:
        base_balance = self.get_base_denomination_balance(address)
        return self.get_amount_from_base_denomination(base_balance)

    def get_transfer_gas_amount(self, address: str, transfer_amount: int, multiplied=False) -> int:
        """
        Get gas amount for accumulation or withdraw in wei
        """
        amount = self.DEFAULT_TRANSFER_GAS_LIMIT

        # sometimes gas estimate is incorrect
        if multiplied:
            amount *= self.DEFAULT_TRANSFER_GAS_MULTIPLIER

        return amount

    def wait_for_balance_in_base_denomination(self, address, sleep_for=15, attempts=3):
        for i in range(attempts):
            balance = self.get_base_denomination_balance(address)
            if balance:
                return balance
            else:
                time.sleep(sleep_for)
        return 0

    def get_accumulation_address(self, accumulation_amount):
        keeper_wallet = self.manager.get_keeper_wallet()
        keeper_balance = self.get_balance(keeper_wallet.address)

        accumulation_address = self.manager.COLD_WALLET_ADDRESS

        if keeper_balance + accumulation_amount < self.keeper_accumulation_balance_limit:
            accumulation_address = keeper_wallet.address

        return accumulation_address

    def __str__(self):
        return f'{self.params.symbol}'


class GasPriceCache:
    """
    Cached gas price so we need to request network less often
    """
    GAS_PRICE_UPDATE_PERIOD: int = None
    GAS_PRICE_COEFFICIENT: int = 1
    MIN_GAS_PRICE: int = None
    MAX_GAS_PRICE: int = None

    def __init__(self, web3: Web3):
        log.info('Init gas price cache')
        self.web3 = web3

    @cachetools.func.ttl_cache(ttl=GAS_PRICE_UPDATE_PERIOD)
    def get_price(self):
        price = self.web3.eth.gasPrice
        log.info('Current gas price: %s', price)

        return price

    def get_increased_price(self, to_compare_price=0):
        """
        We wanna instant transactions
        """
        price = self.get_price()
        price = int(price + (price * self.GAS_PRICE_COEFFICIENT))
        price = max(price, self.MIN_GAS_PRICE)

        if to_compare_price:
            to_compare_price = to_compare_price + int(to_compare_price * 0.1)
            price = max(price, to_compare_price)
            log.info(f'Replaced gas price: {price}')

        price = min(price, self.MAX_GAS_PRICE)
        log.info('Increased gas price: %s', price)
        return price


class BlockchainManager:
    CURRENCY: Currency = None
    TOKEN_CURRENCIES: Dict[Currency, TokenParams] = None
    TOKEN_CLASS: Type[Token] = None
    BASE_DENOMINATION_DECIMALS: int = None
    MIN_BALANCE_TO_ACCUMULATE_DUST: Decimal = None
    COLD_WALLET_ADDRESS: str

    def __init__(self, client):
        log.info(f'Init {self.CURRENCY} manager')
        self.client = client
        self._tokens: List[Token] = []
        self._token_by_address_dict: Dict[str, Token] = {}
        self._token_by_symbol_dict: Dict[str, Token] = {}
        self._register_tokens()

    def get_block(self, block_id):
        raise NotImplementedError

    def get_balance_in_base_denomination(self, address: str):
        raise NotImplementedError

    def get_balance(self, address: str) -> Decimal:
        raise NotImplementedError

    def send_tx(self, private_key, to_address, amount, **kwargs):
        raise NotImplementedError

    def _register_tokens(self):
        """
        Load supported tokens from settings
        """
        log.info('Registering tokens')
        for currency, token_data in self.TOKEN_CURRENCIES.items():
            token = self.TOKEN_CLASS(self.client, token_data, self)
            self._tokens.append(token)
            self._token_by_address_dict[token.params.contract_address] = token
            self._token_by_symbol_dict[token.params.symbol] = token

    @property
    def accumulation_min_balance(self):
        return FeesAndLimits.get_limit(self.CURRENCY.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.MIN_VALUE)

    @property
    def deposit_min_amount(self):
        return FeesAndLimits.get_limit(self.CURRENCY.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE)

    @property
    def keeper_accumulation_balance_limit(self):
        return FeesAndLimits.get_limit(self.CURRENCY.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.KEEPER)

    @property
    def registered_token_addresses(self):
        return list(self._token_by_address_dict)

    @property
    def registered_token_currencies(self):
        return [item.currency for item in self._tokens]

    @property
    def registered_tokens(self):
        return self._tokens

    def get_token_by_symbol(self, symbol: Union[str, Currency]) -> Token:
        """
        Find token by symbol or currency instance
        """
        if isinstance(symbol, Currency):
            symbol = symbol.code

        token = self._token_by_symbol_dict.get(symbol)
        if not token:
            raise UnknownTokenSymbol(symbol)
        return token

    def get_token_by_address(self, address: str) -> Token:
        """
        Find token by contract address
        """
        token = self._token_by_address_dict.get(address)
        if not token:
            raise UnknownTokenAddress(address)
        return token

    @cachetools.func.ttl_cache(ttl=5)
    def get_user_addresses(self) -> List[str]:
        return get_user_addresses(blockchain_currency=self.CURRENCY)

    @cachetools.func.ttl_cache(ttl=60)
    def get_keeper_wallet(self) -> BlockchainAccount:
        return get_keeper_wallet(self.CURRENCY)

    @cachetools.func.ttl_cache(ttl=60)
    def get_gas_keeper_wallet(self) -> BlockchainAccount:
        return get_keeper_wallet(self.CURRENCY, gas_keeper=True)

    def get_user_wallet(self, symbol: Union[str, Currency], address: str) -> BlockchainAccount:
        return get_user_wallet(symbol, address)

    def get_wallet_db_instance(self, symbol: Union[str, Currency], to_addr: str) -> Optional[UserWallet]:
        return UserWallet.objects.filter(
            currency=symbol,
            address__iexact=to_addr,
        ).exclude(
            block_type__in=[UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION]
        ).first()

    @classmethod
    def get_amount_from_base_denomination(cls, amount) -> Decimal:
        return get_amount_from_base_denomination(amount, cls.BASE_DENOMINATION_DECIMALS)

    @classmethod
    def get_base_denomination_from_amount(cls, amount) -> int:
        return get_base_denomination_from_amount(amount, cls.BASE_DENOMINATION_DECIMALS)

    def get_accumulation_address(self, accumulation_amount):
        keeper_wallet = self.get_keeper_wallet()
        keeper_balance = self.get_balance(keeper_wallet.address)

        accumulation_address = self.COLD_WALLET_ADDRESS

        if keeper_balance + accumulation_amount < self.keeper_accumulation_balance_limit:
            accumulation_address = keeper_wallet.address

        return accumulation_address

