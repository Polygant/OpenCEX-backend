import logging
from django.db.models.query import QuerySet

from django.conf import settings
from django.core.management.base import BaseCommand

from cryptocoins.coins.btc import BTC_CURRENCY
from core.consts.currencies import CRYPTO_WALLET_CREATORS, ALL_TOKEN_CURRENCIES
from core.currency import Currency
from core.models.cryptocoins import UserWallet
from cryptocoins.models import GasKeeper
from cryptocoins.models import Keeper
from cryptocoins.utils.btc import generate_btc_multisig_keeper
from cryptocoins.utils.commons import create_keeper
from lib.cipher import AESCoderDecoder

log = logging.getLogger(__name__)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('currency', help='Currency code')
        parser.add_argument('-p', '--password', dest='password', help='Encryption password')
        parser.add_argument('-g', '--gas', dest='gas', action='store_true', help='Is gas keeper')

    def handle(self, *args, **options):
        log.info(options)
        password = options.get('password')
        currency = Currency.get(options.get('currency'))
        is_gas_keeper = options.get('gas')

        if currency == BTC_CURRENCY:
            generate_btc_multisig_keeper(log)
            return

        if currency not in CRYPTO_WALLET_CREATORS or currency in ALL_TOKEN_CURRENCIES:
            raise Exception(f'There is no wallet creator for {currency}')

        wallet_create_fn = CRYPTO_WALLET_CREATORS[currency]
        kwargs = {'user_id': None, 'is_new': True, 'currency': currency}

        new_keeper_wallet: UserWallet = wallet_create_fn(**kwargs)
        if isinstance(new_keeper_wallet, QuerySet):
            new_keeper_wallet = new_keeper_wallet.first()

        if not new_keeper_wallet:
            raise Exception('New wallet was not created')

        if not password and not is_gas_keeper:
            raise Exception('Password required for Keeper generation')

        if password:
            log.info(f'Ecrypt using secret: {password}')
            private_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(new_keeper_wallet.private_key)
            encrypted_key = AESCoderDecoder(password).encrypt(private_key)
            dbl_encrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(encrypted_key)
            new_keeper_wallet.private_key = dbl_encrypted_key
            new_keeper_wallet.save()
            log.info('Wallet successfully encrypted')

        KeeperModel = Keeper
        if is_gas_keeper:
            # if currency not in [ETH_CURRENCY, TRX_CURRENCY]:
            #     raise Exception('Only ETH and TRX GasKeeper can be created')
            KeeperModel = GasKeeper

        create_keeper(new_keeper_wallet, KeeperModel)
