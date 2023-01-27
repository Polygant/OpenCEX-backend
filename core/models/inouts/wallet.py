import logging

import pytz
from django.conf import settings
from django.db import models
from django.db.transaction import atomic
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ValidationError

from core.consts.inouts import DISABLE_TOPUPS
from core.currency import CurrencyModelField
from core.exceptions.inouts import NotEnoughFunds
from core.models import DisabledCoin
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import REASON_WALLET_REVERT_CHARGE
from core.models.inouts.transaction import REASON_WALLET_REVERT_RETURN
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.transaction import Transaction
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.helpers import copy_instance

logger = logging.getLogger('wallet')


class WalletTransactions(BaseModel):
    STATUS_NOT_SET = 0
    STATUS_REVERTED = 99

    STATUS_LIST = (
        (STATUS_NOT_SET, _('Not set')),
        (STATUS_REVERTED, _('Reverted')),
    )

    STATE_NOT_CHECKED = 1
    STATE_ACCUMULATED = 2
    STATE_NOT_ACCUMULATED = 3
    STATE_WRONG_AMOUNT = 4
    STATE_WRONG_ACCUMULATION = 5
    STATE_BAD_DEPOSIT = 6

    STATES = (
        (STATE_NOT_CHECKED, _('Not checked')),
        (STATE_ACCUMULATED, _('Accumulated')),
        (STATE_NOT_ACCUMULATED, _('Not accumulated')),
        (STATE_WRONG_AMOUNT, _('Wrong amount')),
        (STATE_WRONG_ACCUMULATION, _('Wrong accumulation')),
        (STATE_BAD_DEPOSIT, _('Bad deposit')),
    )

    class Meta:
        verbose_name = "Crypto Topup"
        verbose_name_plural = "Crypto Topups"

    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    wallet = models.ForeignKey('core.UserWallet', on_delete=models.CASCADE,
                               related_name='wallet_transaction')
    tx_hash = models.CharField(max_length=250)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE,
                                    related_name='wallet_transaction', null=True)
    status = models.PositiveSmallIntegerField(default=STATUS_NOT_SET, choices=STATUS_LIST)
    state = models.PositiveSmallIntegerField(default=STATE_NOT_CHECKED, choices=STATES)

    def save(self, *args, **kwargs):
        assert self.amount > 0
        with atomic():
            # do not topup old addresses
            new_addresses_date = pytz.UTC.localize(settings.LATEST_ADDRESSES_REGENERATION)

            deposit_min_limit = FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE)
            deposit_max_limit = FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MAX_VALUE)
            accumulation_min_limit = FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.MIN_VALUE)

            if deposit_min_limit > self.amount >= accumulation_min_limit\
                    or DisabledCoin.is_coin_disabled(self.currency, DISABLE_TOPUPS)\
                    or self.wallet.is_deposits_blocked\
                    or self.amount > deposit_max_limit:
                return super(WalletTransactions, self).save(*args, **kwargs)

            do_make_topup = not self.id \
                            and not self.wallet.merchant \
                            and self.wallet.created > new_addresses_date \
                            and not self.wallet.user.restrictions.disable_topups \
                            and not self.state == self.STATE_BAD_DEPOSIT

            if do_make_topup:
                self.topup_tx()

            # self.wallet.add_balance(self.amount)
            return super(WalletTransactions, self).save(*args, **kwargs)

    def topup_tx(self):
        if self.transaction:
            return
        with atomic():
            t = Transaction(reason=REASON_TOPUP,
                            user_id=self.wallet.user_id,
                            currency=self.currency,
                            amount=self.amount,
                            data={'txid': self.tx_hash},
                            state=TRANSACTION_COMPLETED
                            )
            t.save()
            self.transaction = t
            return self

    def _revert(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        try:
            with atomic():
                new_transaction: Transaction = copy_instance(self.transaction, Transaction)
                new_transaction.revert(
                    return_status=REASON_WALLET_REVERT_RETURN,
                    charge_status=REASON_WALLET_REVERT_CHARGE,
                )
                new_transaction.save()
                paygeate_revert = WalletTransactionsRevert(
                    user_id=new_transaction.user_id,
                    transaction=new_transaction,
                    origin_transaction=self.transaction,
                    wallet_transaction=self
                )
                paygeate_revert.save()
                create_or_update_wallet_history_item_from_transaction(
                    new_transaction,
                    instance=self.transaction.wallethistoryitem
                )
                self.status = self.STATUS_REVERTED
                self.save()
        except NotEnoughFunds as e:
            raise ValidationError(f'Not enough funds! '
                                  f'user {new_transaction.user_id}, '
                                  f'{new_transaction.amount} '
                                  f'{new_transaction.currency}'
                                  )

    def revert(self):
        if self.status == self.STATUS_REVERTED:
            raise ValidationError(f'the topup {self.id} has already been reverted!')

        self._revert()


class WalletTransactionsRevert(UserMixinModel, BaseModel):
    wallet_transaction = models.ForeignKey(
        WalletTransactions,
        on_delete=models.CASCADE,
        related_name='wallet_transactions_revert',
    )
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE,
                                    related_name='wallet_tr_reverted_transaction')
    origin_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='wallet_tr_origin_transaction',
        null=True,
        blank=True,
    )
