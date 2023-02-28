import logging
from collections import namedtuple
from typing import List, Union

from django.conf import settings
from django.db.models import Q

from core.consts.currencies import BEP20_CURRENCIES
from core.consts.currencies import ERC20_CURRENCIES
from core.consts.currencies import TRC20_CURRENCIES
from core.currency import Currency
from core.models.cryptocoins import UserWallet
from core.models.inouts.withdrawal import WithdrawalRequest, CREATED, PENDING
from cryptocoins.exceptions import KeeperNotFound
from cryptocoins.exceptions import WalletNotFound
from cryptocoins.models import GasKeeper
from cryptocoins.models import Keeper
from cryptocoins.models import LastProcessedBlock
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)

WalletAccount = namedtuple('WalletAccount', ['address', 'private_key', ])


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


def get_keeper_wallet(symbol: Union[str, Currency], gas_keeper=False) -> WalletAccount:
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

    return WalletAccount(
        address=result[0],
        private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(
            result[1]
        )
    )


def get_user_wallet(symbol: Union[str, Currency], address: str) -> WalletAccount:
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

    return WalletAccount(
        address=result[0],
        private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(
            result[1]
        )
    )


def get_user_addresses(currency: Union[Currency, str]) -> List[str]:
    """
    Get all user registered wallet addresses.
    note: cache may be required due users count increase
    """
    currency = ensure_currency(currency)
    qs = UserWallet.objects.filter(
        currency=currency,
    ).values_list('address', flat=True)
    return list(qs)


def get_withdrawal_requests_to_process(currencies: list, blockchain_currency=''):
    tokens = []
    coins = []
    for cur in currencies:
        if cur in ERC20_CURRENCIES or cur in TRC20_CURRENCIES or cur in BEP20_CURRENCIES:
            tokens.append(cur)
        else:
            coins.append(cur)

    if tokens and not blockchain_currency:
        raise Exception('Blockchain currency not set')

    qs = WithdrawalRequest.objects.filter(
        (Q(currency__in=tokens) & Q(data__blockchain_currency=blockchain_currency)) | Q(currency__in=coins),
        state=CREATED,
        approved=True,
        confirmed=True,
    ).order_by(
        'created',
    ).only(
        'id',
    )

    return qs


def get_withdrawal_requests_pending(currencies: list, blockchain_currency=''):
    # TODO REFACTOR
    common_currencies = []
    not_common_currencies = []
    common_qs = None
    for cur in currencies:
        if cur in ERC20_CURRENCIES or cur in TRC20_CURRENCIES or cur in BEP20_CURRENCIES:
            common_currencies.append(cur)
        else:
            not_common_currencies.append(cur)

    if common_currencies and not blockchain_currency:
        raise Exception('Blockchain currency not set')

    if common_currencies:
        common_qs = WithdrawalRequest.objects.filter(
            currency__in=common_currencies,
            state=PENDING,
            approved=True,
            confirmed=True,
            data__blockchain_currency=blockchain_currency
        ).only(
            'id',
            'txid',
        )

    qs = WithdrawalRequest.objects.filter(
        currency__in=not_common_currencies,
        state=PENDING,
        approved=True,
        confirmed=True,
    ).only(
        'id',
        'txid',
    )

    if common_qs:
        qs = qs.union(common_qs)

    return qs


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
