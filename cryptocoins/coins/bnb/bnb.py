import json
import logging
from decimal import Decimal

import cachetools.func
from django.conf import settings

from core.consts.currencies import BEP20_CURRENCIES
from core.currency import Currency
from cryptocoins.coins.bnb import BNB_CURRENCY
from cryptocoins.coins.bnb.connection import get_w3_connection
from cryptocoins.interfaces.common import GasPriceCache
from cryptocoins.interfaces.web3_commons import Web3Manager, Web3Token, Web3Transaction

log = logging.getLogger(__name__)

BEP20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_from","type":"address"},{"indexed":true,"name":"_to","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_owner","type":"address"},{"indexed":true,"name":"_spender","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Approval","type":"event"}]')  # noqa: 501
DEFAULT_TRANSFER_GAS_LIMIT = 100_000
DEFAULT_TRANSFER_GAS_MULTIPLIER = 2


class BnbTransaction(Web3Transaction):
    pass


class BnbGasPriceCache(GasPriceCache):
    GAS_PRICE_UPDATE_PERIOD = settings.BNB_GAS_PRICE_UPDATE_PERIOD
    GAS_PRICE_COEFFICIENT = settings.BNB_GAS_PRICE_COEFFICIENT
    MIN_GAS_PRICE = settings.BNB_MIN_GAS_PRICE
    MAX_GAS_PRICE = settings.BNB_MAX_GAS_PRICE

    @cachetools.func.ttl_cache(ttl=GAS_PRICE_UPDATE_PERIOD)
    def get_price(self):
        return self.web3.eth.gasPrice


class BEP20Token(Web3Token):
    ABI = BEP20_ABI
    BLOCKCHAIN_CURRENCY: Currency = BNB_CURRENCY
    CHAIN_ID = settings.BNB_CHAIN_ID


class BnbManager(Web3Manager):
    CURRENCY: Currency = BNB_CURRENCY
    TOKEN_CURRENCIES = BEP20_CURRENCIES
    TOKEN_CLASS = BEP20Token
    GAS_PRICE_CACHE_CLASS = BnbGasPriceCache
    CHAIN_ID = settings.BNB_CHAIN_ID
    MIN_BALANCE_TO_ACCUMULATE_DUST = Decimal('0.002')
    COLD_WALLET_ADDRESS = settings.BNB_SAFE_ADDR


w3 = get_w3_connection()
bnb_manager = BnbManager(client=w3)
