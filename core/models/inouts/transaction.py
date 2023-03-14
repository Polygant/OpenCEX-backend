import logging

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db import transaction

from core.currency import CurrencyModelField
from lib.fields import MoneyField
from lib.helpers import to_decimal
from exchange.models import BaseModel
from exchange.models import UserMixinModel

from core.balance_manager import BalanceManager


logger = logging.getLogger('transactions')

REASON_TOPUP = 1
REASON_WITHDRAWAL = 2
REASON_WITHDRAWAL_RET = 3
REASON_TOPUP_MERCHANT = 4

REASON_ORDER_OPENED = 10
REASON_ORDER_EXECUTED = 11
REASON_ORDER_CANCELED = 12
REASON_ORDER_CACHEBACK = 13
REASON_ORDER_EXTRA_CHARGE = 14
REASON_ORDER_CHARGE_RETURN = 15
REASON_ORDER_REVERT_CHARGE = 16
REASON_ORDER_REVERT_RETURN = 17
REASON_PAYGATE_REVERT_CHARGE = 18
REASON_PAYGATE_REVERT_RETURN = 19


REASON_WALLET_REVERT_CHARGE = 24
REASON_WALLET_REVERT_RETURN = 25

REASON_FEE_TOPUP = 30
REASON_BONUS_PAID = 31  # bonus paid
REASON_REF_BONUS = 32  # bonus topup

REASON_STAKE = 40
REASON_UNSTAKE = 41
REASON_LOCK = 42
REASON_UNLOCK = 43

REASON_STAKE_EARNINGS = 44

REASON_MANUAL_TOPUP = 50


ORDER_REASONS = [REASON_ORDER_OPENED,
                 REASON_ORDER_EXECUTED,
                 REASON_ORDER_CANCELED,
                 REASON_ORDER_CACHEBACK,
                 REASON_ORDER_EXTRA_CHARGE,
                 REASON_ORDER_CHARGE_RETURN,
                 REASON_ORDER_REVERT_CHARGE,
                 REASON_ORDER_REVERT_RETURN,
                 ]

MANUAL = 100


TRANSACTION_PENDING = 0
TRANSACTION_COMPLETED = 1
TRANSACTION_CANCELED = 2
TRANSACTION_FAILED = 3

REASONS = {  # 0: 'ZERO',
    REASON_TOPUP: 'Topup',
    REASON_WITHDRAWAL: 'Withdrawal',
    REASON_WITHDRAWAL_RET: 'Withdrawal return',
    REASON_ORDER_OPENED: 'Order set',
    REASON_ORDER_EXECUTED: 'Order executed',
    REASON_ORDER_CANCELED: 'Order canceled',
    REASON_ORDER_CACHEBACK: 'Order cacheback',
    # MANUAL: 'Manual operation', # review and possible remove
    REASON_ORDER_EXTRA_CHARGE: "order extra charge",
    REASON_ORDER_CHARGE_RETURN: 'order partial charge return',
    REASON_FEE_TOPUP: 'fee topup',
    REASON_BONUS_PAID: 'bonus paid',
    REASON_REF_BONUS: 'bonus topup',
    REASON_ORDER_REVERT_CHARGE: 'order revert charge',
    REASON_ORDER_REVERT_RETURN: 'order revert return',
    REASON_PAYGATE_REVERT_CHARGE: 'paygate revert charge',
    REASON_PAYGATE_REVERT_RETURN: 'paygate revert return',
    REASON_WALLET_REVERT_CHARGE: 'wallet revert charge',
    REASON_WALLET_REVERT_RETURN: 'wallet revert return',
    REASON_STAKE: 'Stake',
    REASON_UNSTAKE: 'Unstake',
    REASON_LOCK: 'Lock',
    REASON_UNLOCK: 'Unlock',
    REASON_STAKE_EARNINGS: 'Stake Earnings',
    REASON_MANUAL_TOPUP: 'Manual Topup',
}


# reasons used to increase balance on transaction created! update if add new reasons """
POSITIVE_REASONS = [REASON_TOPUP,
                    REASON_TOPUP_MERCHANT,
                    REASON_ORDER_EXECUTED,
                    REASON_ORDER_CANCELED,
                    REASON_ORDER_CACHEBACK,
                    REASON_ORDER_REVERT_RETURN,
                    REASON_WITHDRAWAL_RET,
                    REASON_ORDER_CHARGE_RETURN,
                    REASON_PAYGATE_REVERT_RETURN,
                    REASON_WALLET_REVERT_RETURN,
                    REASON_FEE_TOPUP,
                    REASON_REF_BONUS,
                    REASON_UNSTAKE,
                    REASON_UNLOCK,
                    REASON_STAKE_EARNINGS,
                    REASON_MANUAL_TOPUP,
                    ]


STATES = {
    TRANSACTION_PENDING: 'Pending',
    TRANSACTION_COMPLETED: 'Completed',
    TRANSACTION_CANCELED: 'Canceled',
    TRANSACTION_FAILED: 'Failed'
}


class Transaction(UserMixinModel, BaseModel):
    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    reason = models.PositiveSmallIntegerField(null=False, blank=False, choices=list(REASONS.items()))
    state = models.PositiveSmallIntegerField(choices=list(STATES.items()), default=TRANSACTION_PENDING, null=False, blank=False)
    data = JSONField(default=dict)
    internal = JSONField(default=dict, blank=True)

    @property
    def is_pending(self):
        return self.state == TRANSACTION_PENDING

    def __str__(self):
        return "<{} {}>[{}] {} {}".format(self.id, self.user.username, str(self.currency), REASONS[self.reason], self.amount)

    def save(self, *args, update_balance_on_adding=True, atomic=True, update_balance_pending=False, **kwargs):
        assert self.state in [TRANSACTION_PENDING, TRANSACTION_COMPLETED]

        def _save():
            if not update_balance_pending and update_balance_on_adding and self._state.adding:
                self.update_balance()

            if update_balance_pending and self.state in [TRANSACTION_PENDING]:
                self.state = TRANSACTION_COMPLETED
                self.update_balance()

            return super(Transaction, self).save(*args, **kwargs)

        if atomic:
            with transaction.atomic():
                return _save()

        else:
            return _save()

    @classmethod
    def create_with_balance_update(cls, data: dict):
        if 'user' in data:
            data['user_id'] = data['user']
            del data['user']

        tx = cls.objects.create(**data)
        tx.update_balance()
        tx.save()

    @transaction.atomic
    def cancel(self, *args, **kwargs):
        assert self._state.adding is False
        assert self.state in [TRANSACTION_PENDING, TRANSACTION_COMPLETED]
        self.state = TRANSACTION_CANCELED
        self.update_balance(cancel=True)
        return super(Transaction, self).save(*args, **kwargs)

    def update_balance(self, cancel=False):
        positive_update = self.reason in POSITIVE_REASONS

        amount = to_decimal(self.amount)
        if cancel:
            positive_update = not positive_update
            amount = - self.amount
            assert (amount > 0) == positive_update

        if positive_update:
            # self.increase_balance2(amount)
            BalanceManager.increase_amount(self.user_id, self.currency, amount)
        else:
            # self.decrease_balance2(amount)
            BalanceManager.decrease_amount(self.user_id, self.currency, amount)

    # def decrease_balance2(self, amount):
    #     amount = to_decimal(amount)
    #     assert amount < 0, Exception(amount)
    #     amount = abs(amount)
    #
    #     result = Balance.objects.filter(
    #         user_id=self.user_id,
    #         currency=self.currency,
    #         amount__gte=F('amount') - amount
    #     ).update(
    #         amount=F('amount') - amount,
    #         # only for order create
    #         amount_in_orders=F('amount_in_orders') + amount,
    #     )
    #
    #     if result != 1:
    #         raise NotEnoughFunds()
    #
    # def increase_balance2(self, amount):
    #     amount = to_decimal(amount)
    #     assert amount > 0, Exception(amount)
    #
    #     result = Balance.objects.filter(
    #         user_id=self.user_id,
    #         currency=self.currency,
    #     ).update(
    #         amount=F('amount') + amount
    #     )
    #
    #     if result != 1:
    #         query = dict(user_id=self.user_id, currency=self.currency)
    #         balance = Balance(amount=amount, **query)
    #         balance.save()

    def revert(self, return_status=REASON_ORDER_REVERT_RETURN, charge_status=REASON_ORDER_REVERT_CHARGE):
        if self.amount < 0:
            self.reason = return_status
        else:
            self.reason = charge_status

        self.amount = self.amount * -1

    @classmethod
    def topup(cls, user_id, currency, amount, data=None, reason=REASON_TOPUP):
        # TODO: remove data from model and all code!
        data = data or {}
        t = cls(reason=reason,
                user_id=user_id,
                currency=currency,
                amount=amount,
                data=data,
                state=TRANSACTION_COMPLETED
                )
        t.save()
        return t

    @classmethod
    def pending(cls, user_id, currency, amount, data=None, reason=REASON_TOPUP):
        # TODO: remove data from model and all code!
        data = data or {}
        t = cls(reason=reason,
                user_id=user_id,
                currency=currency,
                amount=amount,
                data=data,
                state=TRANSACTION_PENDING
                )
        t.save(update_balance_on_adding=False)
        return t

    @classmethod
    def withdrawal(cls, user_id, currency, amount, data=None, state=TRANSACTION_PENDING, reason=REASON_WITHDRAWAL):
        # TODO: remove data from model and all code!
        data = data or {}
        assert amount < 0
        t = cls(reason=reason,
                user_id=user_id,
                currency=currency,
                amount=amount,
                data=data,
                state=state
                )
        t.save()
        return t

    class Meta:
        indexes = [
            models.Index(fields=['created', 'updated']),
            # inouts.Index(fields=['currency']),
        ]
