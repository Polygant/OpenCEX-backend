from django.conf import settings
from django.db import models

from core.currency import CurrencyModelField


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

    @property
    def is_deposits_blocked(self):
        return self.block_type in [self.BLOCK_TYPE_DEPOSIT, self.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION]

    def __str__(self):
        return f'{self.currency} {self.address}(blockchain={self.blockchain_currency})'

    class Meta:
        unique_together = ('currency', 'address')
