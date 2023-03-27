import logging
from typing import List, Union

from django.conf import settings

from core.consts.currencies import BlockchainAccount
from core.currency import Currency
from cryptocoins.exceptions import KeeperNotFound
from cryptocoins.exceptions import WalletNotFound
from cryptocoins.models.keeper import GasKeeper
from cryptocoins.models.keeper import Keeper
from cryptocoins.models.last_processed_block import LastProcessedBlock
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)


def store_last_processed_block_id(currency: Currency, block_id: int):
    last_processed_block_instance, _ = LastProcessedBlock.objects.get_or_create(
        currency=currency,
        defaults={
            'currency': currency,
        }
    )
    if last_processed_block_instance.block_id >= block_id:
        return
    last_processed_block_instance.block_id = block_id
    last_processed_block_instance.save()


def load_last_processed_block_id(currency: Currency, default: int = 0) -> int:
    last_processed_block_instance = LastProcessedBlock.objects.filter(
        currency=currency,
    ).first()

    if last_processed_block_instance is None:
        log.warning('Last processed block ID not found for %s, return default (%s)', currency, default)

        return default

    return last_processed_block_instance.block_id


def ensure_currency(currency: [Currency, str]) -> Currency:
    if isinstance(currency, str):
        currency = Currency.get(currency)

    return currency


def get_keeper_wallet(symbol: Union[str, Currency], gas_keeper=False) -> BlockchainAccount:
    Model = GasKeeper if gas_keeper else Keeper
    currency = ensure_currency(symbol)

    result = Model.objects.filter(
        currency=currency,
    ).only(
        'user_wallet__address',
        'user_wallet__private_key',
    ).values_list(
        'user_wallet__address',
        'user_wallet__private_key',
    ).first()

    if result is None:
        raise KeeperNotFound(currency.code)

    return BlockchainAccount(
        address=result[0],
        private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(
            result[1]
        )
    )


def get_user_wallet(symbol: Union[str, Currency], address: str) -> BlockchainAccount:
    from core.models.cryptocoins import UserWallet

    currency = ensure_currency(symbol)

    result = UserWallet.objects.filter(
        currency=currency,
        address=address,
    ).only(
        'address',
        'private_key',
    ).values_list(
        'address',
        'private_key',
    ).first()

    if result is None:
        raise WalletNotFound(currency.code)

    return BlockchainAccount(
        address=result[0],
        private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(
            result[1]
        )
    )


def get_user_addresses(currency: List[Union[Currency, str]] = None, blockchain_currency: Union[Currency, str] = None) -> List[str]:
    """
    Get all user registered wallet addresses.
    note: cache may be required due users count increase
    """
    from core.models.cryptocoins import UserWallet
    currency = ensure_currency(currency)
    qs = UserWallet.objects.all()
    if currency:
        qs = UserWallet.objects.filter(
            currency__in=currency,
        )
    if blockchain_currency:
        qs = qs.filter(blockchain_currency=blockchain_currency)
    return list(qs.values_list('address', flat=True))


def create_keeper(user_wallet, KeeperModel=Keeper, extra=None):
    keeper = KeeperModel.objects.filter(
        currency=user_wallet.currency
    ).first()

    if not keeper:
        keeper = KeeperModel.objects.create(
            currency=user_wallet.currency,
            user_wallet=user_wallet
        )
    else:
        keeper.user_wallet = user_wallet

    if extra and isinstance(extra, dict):
        keeper.extra = extra
    keeper.save()
    log.info('New keeper successfully created')
    log.info(f'Address: {user_wallet.address}, Currency: {user_wallet.currency}')
    return keeper
