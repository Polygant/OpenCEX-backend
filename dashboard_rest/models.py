from django.contrib.auth.models import User

from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import WithdrawalRequest
from core.models.orders import ExecutionResult


class Topups(WalletTransactions):
    class Meta:
        proxy = True


class Withdrawals(WithdrawalRequest):
    class Meta:
        proxy = True


class TradeFee(ExecutionResult):
    class Meta:
        proxy = True


class WithdrawalFee(WithdrawalRequest):
    class Meta:
        proxy = True


class CommonUsersStats(User):
    class Meta:
        proxy = True


class CommonInouts(WalletTransactions):
    class Meta:
        proxy = True


class TradeVolume(ExecutionResult):
    class Meta:
        proxy = True
