from django.contrib.auth.models import User, UserManager
from django.db.models.aggregates import Count

from core.models.cryptocoins import UserWallet
from core.models.facade import UserFee, UserKYC
from core.models.inouts.balance import Balance as BaseBalance
from core.models.inouts.transaction import Transaction as BaseTransaction
from core.models.inouts.withdrawal import WithdrawalRequest as BaseWithdrawalRequest
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.models.stats import UserPairDailyStat as BaseUserPairDailyStat


class ExchangeFee(UserFee):
    class Meta:
        proxy = True


class Balance(BaseBalance):

    class Meta:
        proxy = True


class Transaction(BaseTransaction):

    class Meta:
        proxy = True


class Topups(BaseTransaction):

    class Meta:
        proxy = True


class Withdrawal(BaseTransaction):

    class Meta:
        proxy = True


class AllOrder(Order):

    class Meta:
        proxy = True


class AllOrderNoBot(Order):

    class Meta:
        proxy = True


class Match(ExecutionResult):

    class Meta:
        proxy = True


class WithdrawalRequest(BaseWithdrawalRequest):
    class Meta:
        proxy = True


class UserDailyStat(BaseUserPairDailyStat):
    class Meta:
        proxy = True


class RefManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().order_by().annotate(ref_count=Count('owner_user')).filter(ref_count__gt=0)

    def select_related(self, *args, **kwargs):
        return self


class RefDetails(User):
    class Meta:
        verbose_name_plural = 'Ref program details'
        proxy = True

    objects = RefManager()


class UserKYCProxy(UserKYC):
    class Meta:
        verbose_name = 'User KYC'
        verbose_name_plural = 'Users KYC'
        proxy = True


class BalanceSummary(BaseBalance):
    class Meta:
        proxy = True


class ExchangeUser(User):
    class Meta:
        proxy = True
