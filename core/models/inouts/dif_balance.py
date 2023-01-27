from datetime import datetime

from django.db import models
from django.db.models import Sum, Q

from core.consts.dif_balance import TYPES, TYPE_BALANCE
from core.currency import CurrencyModelField
from core.models import Balance, Transaction
from core.models.inouts.transaction import TRANSACTION_COMPLETED, TRANSACTION_PENDING
from core.models.inouts.transaction import TRANSACTION_CANCELED, TRANSACTION_FAILED
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.utils import suppress_autotime


class DifBalanceAbstract(UserMixinModel):
    TYPE_LIST = TYPES

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)
    type = models.IntegerField(default=TYPE_BALANCE, choices=TYPES.items(), null=False, blank=False)
    currency = CurrencyModelField(db_index=True, blank=True, null=True)
    diff = MoneyField(default=0)
    diff_percent = MoneyField(default=0)
    balance = MoneyField(default=0)
    old_balance = MoneyField(default=0)
    calc_balance = MoneyField(default=0)
    txs_amount = MoneyField(default=0)
    sum_diff = MoneyField(default=0)

    class Meta:
        abstract=True

    def __str__(self):
        if self.currency:
            return '{} {} {} {} {} {}'.format(
                self.created,
                self.user.username,
                self.TYPE_LIST[self.type],
                self.currency.code,
                self.diff_percent,
                self.diff,
            )

        return '{} {} {} {} {}'.format(
            self.created,
            self.user.username,
            self.TYPE_LIST[self.type],
            self.diff_percent,
            self.diff,
        )

    @classmethod
    def process(cls):
        current_time = datetime.now()
        balances = Balance.objects.all()
        for balance in balances:
            curr_balance = balance.amount
            old_balance: cls = cls.objects.filter(
                user=balance.user,
                currency=balance.currency,
                type=TYPE_BALANCE
            ).last()

            if old_balance:
                sum_amount = Transaction.objects.filter(
                    (
                        Q(created__lte=current_time) &
                        Q(created__gt=old_balance.created) &
                        Q(state__in=[TRANSACTION_COMPLETED, TRANSACTION_PENDING])
                    ),
                    user=balance.user,
                    currency=balance.currency,
                ).aggregate(sum=Sum('amount'))['sum'] or 0

                # skip created/pending and then cancelled/failed txs in same period
                cancelled_amount = Transaction.objects.filter(
                    (
                        Q(updated__lte=current_time) &
                        Q(updated__gt=old_balance.created) &
                        Q(state__in=[TRANSACTION_CANCELED, TRANSACTION_FAILED])
                    ),
                    ~Q(
                        Q(created__lte=current_time) &
                        Q(created__gt=old_balance.created) &
                        Q(state__in=[TRANSACTION_CANCELED, TRANSACTION_FAILED]),
                    ),
                    user=balance.user,
                    currency=balance.currency,
                ).aggregate(sum=Sum('amount'))['sum'] or 0

                calculated_balance = old_balance.balance + sum_amount - cancelled_amount
                diff = curr_balance - calculated_balance
                diff_percent = diff / curr_balance if curr_balance else 0

                dif = cls(
                    user=balance.user,
                    currency=balance.currency,
                    diff=diff,
                    diff_percent=diff_percent,
                    balance=curr_balance,
                    old_balance=old_balance.balance,
                    txs_amount=sum_amount,
                    calc_balance=calculated_balance,
                    sum_diff=old_balance.sum_diff + diff
                )
                with suppress_autotime(dif, ['created']):
                    dif.created = current_time
                    dif.save()
            else:
                sum_amount = Transaction.objects.filter(
                    user=balance.user,
                    currency=balance.currency,
                    created__lte=current_time  # get transaction only before start process
                ).aggregate(sum=Sum('amount'))['sum'] or 0

                diff = curr_balance - sum_amount
                diff_percent = diff / curr_balance if curr_balance else 0

                dif = cls(
                    user=balance.user,
                    currency=balance.currency,
                    diff=curr_balance - sum_amount,
                    diff_percent=diff_percent,
                    balance=curr_balance,
                    old_balance=sum_amount,
                    txs_amount=sum_amount,
                    calc_balance=sum_amount,
                    sum_diff=0
                )
                with suppress_autotime(dif, ['created']):
                    dif.created = current_time
                    dif.save()


class DifBalance(DifBalanceAbstract):
    pass


class DifBalanceMonth(DifBalanceAbstract):
    pass
