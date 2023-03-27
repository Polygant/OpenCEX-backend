import logging

from eth_account import Account
from eth_utils.curried import combomethod
from eth_utils.curried import keccak
from eth_utils.curried import text_if_str
from eth_utils.curried import to_bytes

from core.consts.currencies import BlockchainAccount
from lib.cryptointegrator.tasks import create_wallet

log = logging.getLogger(__name__)


class PassphraseAccount(Account):

    @combomethod
    def create(self, passphrase):
        extra_key_bytes = text_if_str(to_bytes, passphrase)
        key_bytes = keccak(extra_key_bytes)
        return self.privateKeyToAccount(key_bytes)


def get_wallet_data(user_id, currency, is_new=False):
    from core.models.cryptocoins import UserWallet

    f = create_wallet.apply_async([user_id, is_new], queue=currency.code.lower())
    w_id = f.get(timeout=30)

    return UserWallet.objects.filter(id=w_id)


def get_latest_block_id(currency):
    from cryptocoins.coins.btc import BTC_CURRENCY

    if currency == BTC_CURRENCY:
        from cryptocoins.coins.btc.service import BTCCoinService
        service = BTCCoinService()
    else:
        raise Exception(f'Currency {currency} not found')
    block_id = service.get_current_block_id()
    return block_id


def generate_new_wallet_account(currency) -> BlockchainAccount:
    from cryptocoins.coins.btc import BTC_CURRENCY
    from cryptocoins.coins.eth import ETH_CURRENCY
    from cryptocoins.coins.trx import TRX_CURRENCY
    from cryptocoins.coins.bnb import BNB_CURRENCY
    from cryptocoins.coins.eth.wallet import create_new_blockchain_account as create_eth_wallet
    from cryptocoins.coins.trx.wallet import create_new_blockchain_account as create_trx_wallet

    if currency == BTC_CURRENCY:
        from cryptocoins.coins.btc.service import BTCCoinService
        service = BTCCoinService()
        wallet_account = service.create_new_wallet()
    elif currency in [ETH_CURRENCY, BNB_CURRENCY]:
        wallet_account = create_eth_wallet()
    elif currency == TRX_CURRENCY:
        wallet_account = create_trx_wallet()
    else:
        raise Exception(f'Currency {currency} not found')

    return wallet_account
