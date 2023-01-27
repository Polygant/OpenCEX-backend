import traceback

from rest_framework.exceptions import ValidationError
from lib.exceptions import BaseError


class NotEnoughFunds(BaseError):
    default_detail = 'NotEnoughFunds'
    default_code = 'NotEnoughFunds'


class NotEnoughHold(BaseError):
    default_detail = 'NotEnoughHold'
    default_code = 'NotEnoughHold'


class BadAmount(BaseError):
    default_code = 'bad_amount'
    default_detail = 'Bad amount'


class WithdrawalAlreadyConfirmed(BaseError):
    default_code = 'withdrawal_already_confirmed'
    default_detail = 'Withdrawal request already confirmed'
