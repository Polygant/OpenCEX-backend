import logging
import secrets

from django.conf import settings
from django.db import transaction
from eth_account import Account
from web3 import Web3

from cryptocoins.coins.matic.consts import MATIC
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)


def create_matic_address():
    while 1:
        private_key = Web3.to_hex(secrets.token_bytes(32))
        account = Account.from_key(private_key)

        encrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(
            private_key
        )
        decrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(encrypted_key)

        if decrypted_key.startswith('0x') and len(decrypted_key) == 66:
            break

    return account.address, encrypted_key


@transaction.atomic
def get_or_create_matic_wallet(user_id, is_new=False):
    """
    Make new user wallet and related objects if not exists
    """
    # implicit logic instead of get_or_create
    from core.models.cryptocoins import UserWallet

    user_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=MATIC,
        blockchain_currency=MATIC,
    ).order_by('-id').first()

    if not is_new and user_wallet is not None:
        return user_wallet

    address, encrypted_key = create_matic_address()

    user_wallet = UserWallet.objects.create(
        user_id=user_id,
        currency=MATIC,
        address=address,
        private_key=encrypted_key,
        blockchain_currency=MATIC,
    )

    return user_wallet


@transaction.atomic
def get_or_create_erc20_polygon_wallet(user_id, token_currency, is_new=False):
    from core.models.cryptocoins import UserWallet

    erc20_polygon_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=token_currency,
        blockchain_currency=MATIC,
    ).order_by('-id').first()

    if not is_new and erc20_polygon_wallet is not None:
        return erc20_polygon_wallet

    address, encrypted_key = create_matic_address()

    erc20_polygon_wallet = UserWallet.objects.create(
        user_id=user_id,
        address=address,
        private_key=encrypted_key,
        currency=token_currency,
        blockchain_currency=MATIC,
    )

    return erc20_polygon_wallet


def is_valid_matic_address(address):
    return Web3.is_address(address)


def matic_wallet_creation_wrapper(user_id, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_matic_wallet(
        user_id,
        is_new=is_new,
    )
    return UserWallet.objects.filter(id=wallet.id)


def erc20_polygon_wallet_creation_wrapper(user_id, currency, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_erc20_polygon_wallet(
        user_id,
        token_currency=currency,
        is_new=is_new,
    )
    return UserWallet.objects.filter(id=wallet.id)
