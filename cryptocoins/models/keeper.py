from django.db import models
from django.db.models import JSONField

from core.currency import CurrencyModelField
from exchange.models import BaseModel


class Keeper(BaseModel):
    currency = CurrencyModelField(db_index=True, unique=True)
    user_wallet = models.OneToOneField('core.UserWallet', null=True, on_delete=models.DO_NOTHING)
    # json field need for extra keeper data: redeemScript, cosigners address, public keys etc
    extra = JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return f'Keeper for {self.currency}: {self.user_wallet.address}'


class GasKeeper(BaseModel):
    currency = CurrencyModelField(db_index=True, unique=True)
    user_wallet = models.OneToOneField('core.UserWallet', null=True, on_delete=models.DO_NOTHING)
    # json field need for extra keeper data: redeemScript, cosigners address, public keys etc
    extra = JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return f'Gas keeper for {self.currency}: {self.user_wallet.address}'
