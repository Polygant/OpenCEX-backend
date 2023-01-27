from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.currency import BTC, ETH, USDT
from core.models.cryptocoins import UserWallet
from lib.cipher import AESCoderDecoder

User = get_user_model()


class Command(BaseCommand):

    def add_arguments(self, parser):
        # parser.add_argument('user', help='user id')
        pass

    def handle(self, *args, **options):
        wallets = UserWallet.objects.filter(
            currency__in=[BTC]
        ).exclude(
            private_key='-',
        )
        print('Begin Btc encrypt')
        self.encrypt(wallets)

        wallets = UserWallet.objects.filter(
            currency__in=[ETH, USDT]
        ).exclude(
            private_key='-',
        )
        print('Begin Eth,Usdt encrypt')
        self.encrypt(wallets)

    def encrypt(self, wallets):
        skip = 0
        count = wallets.count()
        for wallet in wallets:
            try:
                pv = AESCoderDecoder(settings.CRYPTO_KEY_OLD).decrypt(wallet.private_key)
                if pv == '':
                    raise Exception()

                wallet.private_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(pv)
                wallet.save()
            except Exception:
                skip += 1
                pass
        print('end encrypt %s/%s' % (count - skip, count))
