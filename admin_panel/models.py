from allauth.account.models import EmailAddress
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


class MetaMixIn:
    class Meta:
        proxy = True


class ExchangeUser(User):
    class Meta:
        proxy = True

    @property
    def balances(self):
        return Balance.for_user(self).items()


class EmailAddressVerified(MetaMixIn, EmailAddress):
    pass


class ExchangeFee(MetaMixIn, UserFee):
    pass


class Balance(MetaMixIn, BaseBalance):
    pass


class Transaction(MetaMixIn, BaseTransaction):
    pass


class Topups(MetaMixIn, BaseTransaction):
    pass


class Withdrawal(MetaMixIn, BaseTransaction):
    pass


class AllOrder(MetaMixIn, Order):
    pass


class AllOrderNoBot(MetaMixIn, Order):
    pass


class Match(MetaMixIn, ExecutionResult):
    pass


class WithdrawalRequest(MetaMixIn, BaseWithdrawalRequest):
    pass


class UserDailyStat(MetaMixIn, BaseUserPairDailyStat):
    pass


class RefManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().order_by().annotate(ref_count=Count('owner_user')).filter(ref_count__gt=0)

    def select_related(self):
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


class BlockedAddresses(UserWallet):
    class Meta:
        verbose_name_plural = 'Blocked Addresses'
        proxy = True
