from django.conf import settings
from django.db import models
from django.db.transaction import atomic

from core.consts.currencies import CRYPTO_WALLET_ACCOUNT_CREATORS
from core.consts.currencies import BlockchainAccount
from core.currency import CurrencyModelField
from lib.cipher import AESCoderDecoder


class UserWallet(models.Model):
    BLOCK_TYPE_NOT_BLOCKED = 0
    BLOCK_TYPE_DEPOSIT = 1
    BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION = 2

    BLOCK_TYPES = (
        (BLOCK_TYPE_NOT_BLOCKED, 'Not blocked'),
        (BLOCK_TYPE_DEPOSIT, 'Deposits'),
        (BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION, 'Deposits + Accumulations'),
    )

    user = models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    currency = CurrencyModelField(db_index=True)
    blockchain_currency = CurrencyModelField(default='BTC')
    address = models.TextField(db_index=True)
    private_key = models.TextField(null=True, blank=True)
    merchant = models.BooleanField(default=False)
    block_type = models.SmallIntegerField(choices=BLOCK_TYPES, default=BLOCK_TYPE_NOT_BLOCKED)
    is_old = models.BooleanField(default=False)

    class Meta:
        unique_together = ('currency', 'address')

    @property
    def is_deposits_blocked(self):
        return self.block_type in [self.BLOCK_TYPE_DEPOSIT, self.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION]

    def regenerate(self):
        """Marks current wallet as old. Creates new 'clean' wallet."""
        wallet_account: BlockchainAccount = CRYPTO_WALLET_ACCOUNT_CREATORS[self.blockchain_currency]()
        with atomic():
            new_user_wallet = UserWallet.objects.create(
                user_id=self.user_id,
                currency=self.currency,
                blockchain_currency=self.blockchain_currency,
                address=wallet_account.address,
                private_key=AESCoderDecoder(settings.CRYPTO_KEY).encrypt(
                    wallet_account.private_key
                ),
            )
            self.is_old = True
            self.save()
            return new_user_wallet

    def unblock(self):
        self.block_type = self.BLOCK_TYPE_NOT_BLOCKED
        super(UserWallet, self).save()

    def __str__(self):
        res = f'{self.currency}'
        if self.blockchain_currency != self.currency:
            res += f'({self.blockchain_currency})'
        res += f' {self.address}'
        if self.is_old:
            res += ' OLD'
        if self.block_type != self.BLOCK_TYPE_NOT_BLOCKED:
            res += ' Blocked'
        return res
