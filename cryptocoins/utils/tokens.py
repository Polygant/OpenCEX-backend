from typing import Dict

from core.consts.currencies import BEP20_CURRENCIES
from core.consts.currencies import ERC20_CURRENCIES
from core.consts.currencies import TRC20_CURRENCIES
from core.currency import Currency, TokenParams


def get_token_contract_address(token_currency_code: str, blockchain_currency_code: str):
    if isinstance(token_currency_code, Currency):
        token_currency_code = token_currency_code.code
    if isinstance(blockchain_currency_code, Currency):
        blockchain_currency_code = blockchain_currency_code.code

    blockchain_tokens_dict: [str, Dict[Currency, TokenParams]] = {
        'ETH': ERC20_CURRENCIES,
        'TRX': TRC20_CURRENCIES,
        'BNB': BEP20_CURRENCIES,
    }

    if blockchain_currency_code not in blockchain_tokens_dict:
        raise Exception(f'Blockchain currency {blockchain_currency_code} in not registered')

    token_params = blockchain_tokens_dict[blockchain_currency_code].get(Currency.get(token_currency_code))
    if not token_params:
        raise Exception(f'Contract address not found for {token_currency_code}')
    return token_params.contract_address