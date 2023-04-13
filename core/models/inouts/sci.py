from django.db import models
from django.db.models import JSONField
from django.db.transaction import atomic
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ValidationError

from core.consts.gates import GATES
from core.currency import CurrencyModelField
from core.exceptions.inouts import NotEnoughFunds
from core.models.inouts.transaction import Transaction, REASON_PAYGATE_REVERT_RETURN, REASON_PAYGATE_REVERT_CHARGE
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.helpers import copy_instance

PENDING = 0
COMPLETED = 1
FAILED = 2

STATES = {
    PENDING: 'Pending',
    COMPLETED: 'Completed',
    FAILED: 'Failed',
}


def name2id(name):
    for id, v in GATES.items():
        if v.NAME == name:
            return id
    raise Exception('no gate!')


class PayGateTopup(BaseModel, UserMixinModel):
    STATUS_NOT_SET = 0
    STATUS_REVERTED = 99

    STATUS_LIST = (
        (STATUS_NOT_SET, _('Not set')),
        (STATUS_REVERTED, _('Reverted')),
    )

    # user, amount, currency
    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    state = models.IntegerField(choices=STATES.items(), default=PENDING, null=False, blank=False)
    data = JSONField(default=dict)
    tx = models.ForeignKey(Transaction, on_delete=models.CASCADE, null=True, related_name='paygate_topup')
    gate_id = models.IntegerField(choices=GATES.items(), null=False, blank=False)
    our_fee_amount = MoneyField(default=0)
    status = models.PositiveSmallIntegerField(default=STATUS_NOT_SET, choices=STATUS_LIST)

    STATE_PENDING = PENDING
    STATE_COMPLETED = COMPLETED
    STATE_FAILED = FAILED

    STATES = STATES

    @property
    def gate(self):
        return GATES[self.gate_id]

    @property
    def topup_id(self):
        return self.gate.topup_id(self)

    @property
    def topup_url(self):
        return self.gate.topup_url(self)

    @classmethod
    def update_from_notification(cls, gate_id, data):
        gate = GATES[gate_id]
        gate.update_topup(cls, data)

    def _revert(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        try:
            with atomic():
                new_transaction: Transaction = copy_instance(self.tx, Transaction)
                new_transaction.revert(
                    return_status=REASON_PAYGATE_REVERT_RETURN,
                    charge_status=REASON_PAYGATE_REVERT_CHARGE,
                )
                new_transaction.save()
                paygeate_revert = PayGateTopupRevert(
                    user_id=new_transaction.user_id,
                    transaction=new_transaction,
                    origin_transaction=self.tx,
                    paygate_topup=self,
                )
                paygeate_revert.save()
                create_or_update_wallet_history_item_from_transaction(
                    new_transaction,
                    instance=self.tx.wallethistoryitem
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

        if self.state not in [self.STATE_COMPLETED, ]:
            raise ValidationError(f'the topup {self.id} was not completed!')

        self._revert()

    def __str__(self):
        return (f'{self.__class__.__name__} #{self.id} {self.gate.NAME} '
                f'{self.currency} {self.amount} {self.get_state_display()}')


class PayGateTopupRevert(UserMixinModel, BaseModel):
    paygate_topup = models.ForeignKey(
        PayGateTopup,
        on_delete=models.CASCADE,
        related_name='paygate_topup_revert',
    )
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='paygate_reverted_transaction')
    origin_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='paygate_origin_transaction',
        null=True,
        blank=True
    )
