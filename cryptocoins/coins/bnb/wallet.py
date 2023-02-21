import logging

from django.conf import settings
from django.db import transaction
from pywallet import wallet as pwallet
from web3 import Web3

from cryptocoins.utils.wallet import PassphraseAccount
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)


@transaction.atomic
def get_or_create_bnb_wallet(user_id, is_new=False):
    """
    Make new user wallet and related objects if not exists
    """
    # implicit logic instead of get_or_create
    from core.models.cryptocoins import UserWallet
    from cryptocoins.coins.bnb import BNB_CURRENCY

    user_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=BNB_CURRENCY,
        blockchain_currency=BNB_CURRENCY,
    ).order_by('-id').first()

    if not is_new and user_wallet is not None:
        return user_wallet

    while 1:
        account = PassphraseAccount.create(pwallet.generate_mnemonic())

        encrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(
            Web3.toHex(account.privateKey)
        )
        decrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(encrypted_key)

        if decrypted_key.startswith('0x') and len(decrypted_key) == 66:
            break

    user_wallet = UserWallet.objects.create(
        user_id=user_id,
        currency=BNB_CURRENCY,
        address=account.address,
        private_key=encrypted_key,
        blockchain_currency=BNB_CURRENCY
    )

    return user_wallet


@transaction.atomic
def get_or_create_bep20_wallet(user_id, currency, is_new=False):
    from core.models.cryptocoins import UserWallet
    from cryptocoins.coins.bnb import BNB_CURRENCY

    bnb_wallet = get_or_create_bnb_wallet(user_id, is_new=is_new)

    bep20_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=currency,
        blockchain_currency=BNB_CURRENCY
    ).first()

    if not is_new and bep20_wallet is not None:
        return bep20_wallet

    bep20_wallet = UserWallet.objects.create(
        user_id=user_id,
        currency=currency,
        address=bnb_wallet.address,
        private_key=bnb_wallet.private_key,
        blockchain_currency=BNB_CURRENCY
    )

    return bep20_wallet


def is_valid_bnb_address(address):
    return Web3.isAddress(address)


def bnb_wallet_creation_wrapper(user_id, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_bnb_wallet(user_id, is_new=is_new)
    return UserWallet.objects.filter(id=wallet.id)


def bep20_wallet_creation_wrapper(user_id, currency, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_bep20_wallet(user_id, currency=currency, is_new=is_new)
    return UserWallet.objects.filter(id=wallet.id)
