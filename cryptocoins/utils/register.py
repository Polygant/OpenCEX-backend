import logging
from typing import Dict, Optional, Callable

from core.consts.currencies import ALL_CURRENCIES, CRYPTO_COINS_PARAMS
from core.consts.currencies import ALL_TOKEN_CURRENCIES
from core.consts.currencies import CRYPTO_ADDRESS_VALIDATORS
from core.consts.currencies import CRYPTO_WALLET_CREATORS
from core.consts.currencies import CURRENCIES_LIST
from core.consts.currencies import ERC20_CURRENCIES
from core.currency import Currency, TokenParams, CoinParams

log = logging.getLogger(__name__)


def register_coin(currency_id: int, currency_code: str, *,
                  address_validation_fn: Optional[Callable] = None,
                  wallet_creation_fn: Optional[Callable] = None,
                  latest_block_fn: Optional[Callable] = None,
                  blocks_diff_alert: Optional[int] = None,
                  encrypted_cold_wallet: Optional[bytes] = None):

    currency = Currency(currency_id, currency_code)
    if currency not in ALL_CURRENCIES:
        if not address_validation_fn:
            log.warning(f'Address validation FN not specified for {currency}')
        if not wallet_creation_fn:
            log.warning(f'Wallet creation FN not specified for {currency}')
        if not latest_block_fn:
            log.warning(f'Latest block FN not specified for {currency}')

        ALL_CURRENCIES.append(currency)
        CURRENCIES_LIST.append((currency_id, currency_code,))
        CRYPTO_ADDRESS_VALIDATORS.update({currency: address_validation_fn})
        CRYPTO_WALLET_CREATORS.update({currency: wallet_creation_fn})
        CRYPTO_COINS_PARAMS.update({
            currency: CoinParams(
                latest_block_fn=latest_block_fn,
                blocks_monitoring_diff=blocks_diff_alert,
                encrypted_cold_wallet=encrypted_cold_wallet,
            )
        })

        log.debug(f'Coin {currency_code} registered')
    return currency


def register_token(currency_id, currency_code, blockchains: Optional[Dict[str, TokenParams]] = None):
    # if not isinstance(blockchains, list) or not blockchains:
    #     raise Exception('blockchains must be type of "list" and cannot be empty')

    currency = Currency(currency_id, currency_code, is_token=True)

    if currency not in ALL_CURRENCIES:
        ALL_CURRENCIES.append(currency)
        CURRENCIES_LIST.append((currency_id, currency_code,))

    if blockchains:
        wallet_creators = {}
        address_validators = {}

        if 'ETH' in blockchains:
            from cryptocoins.coins.eth.wallet import erc20_wallet_creation_wrapper, is_valid_eth_address

            ERC20_CURRENCIES.update({
                currency: blockchains['ETH']
            })
            wallet_creators['ETH'] = erc20_wallet_creation_wrapper
            address_validators['ETH'] = is_valid_eth_address

            log.debug(f'Token {currency} registered as ERC20')

        CRYPTO_WALLET_CREATORS[currency] = wallet_creators
        CRYPTO_ADDRESS_VALIDATORS[currency] = address_validators
        currency.set_blockchain_list(list(blockchains))

    if currency not in ALL_TOKEN_CURRENCIES:
        ALL_TOKEN_CURRENCIES.append(currency)

    return currency
