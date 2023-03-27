import logging

from django.conf import settings
from django.db import transaction
from tronpy.keys import PrivateKey

from core.consts.currencies import BlockchainAccount
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)


def create_trx_address():
    while 1:
        account = PrivateKey.random()
        private_key = account.hex()
        address = account.public_key.to_base58check_address()

        encrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(private_key)
        decrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(encrypted_key)

        if decrypted_key == private_key:
            break
    return address, encrypted_key


def create_new_blockchain_account() -> BlockchainAccount:
    address, encrypted_pk = create_trx_address()
    return BlockchainAccount(
        address=address,
        private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(encrypted_pk),
    )


@transaction.atomic
def get_or_create_trx_wallet(user_id, is_new=False):
    """
    Make new user wallet and related objects if not exists
    """
    # implicit logic instead of get_or_create
    from core.models.cryptocoins import UserWallet
    from cryptocoins.coins.trx import TRX_CURRENCY

    user_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=TRX_CURRENCY,
        blockchain_currency=TRX_CURRENCY,
    ).order_by('-id').first()

    if not is_new and user_wallet is not None:
        return user_wallet

    address, encrypted_key = create_trx_address()

    user_wallet = UserWallet.objects.create(
        user_id=user_id,
        address=address,
        private_key=encrypted_key,
        currency=TRX_CURRENCY,
        blockchain_currency=TRX_CURRENCY
    )

    return user_wallet


@transaction.atomic
def get_or_create_trc20_wallet(user_id, currency, is_new=False):
    from core.models.cryptocoins import UserWallet
    from cryptocoins.coins.trx import TRX_CURRENCY

    trx_wallet = get_or_create_trx_wallet(user_id, is_new=is_new)

    trc20_wallet = UserWallet.objects.filter(
        user_id=user_id,
        currency=currency,
        blockchain_currency=TRX_CURRENCY,
    ).order_by('-id').first()

    if not is_new and trc20_wallet is not None:
        return trc20_wallet

    address, encrypted_key = create_trx_address()

    trc20_wallet = UserWallet.objects.create(
        user_id=user_id,
        address=address,
        private_key=encrypted_key,
        currency=currency,
        blockchain_currency=TRX_CURRENCY
    )

    return trc20_wallet


def trx_wallet_creation_wrapper(user_id, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_trx_wallet(user_id, is_new=is_new)
    return UserWallet.objects.filter(id=wallet.id)


def trx20_wallet_creation_wrapper(user_id, currency, is_new=False, **kwargs):
    from core.models.cryptocoins import UserWallet

    wallet = get_or_create_trc20_wallet(user_id, currency=currency, is_new=is_new)
    return UserWallet.objects.filter(id=wallet.id)
