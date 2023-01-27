from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from rest_framework import status

from lib.exceptions import BaseError


class SOFAlreadySetError(BaseError):
    default_detail = _('Already set.')
    default_code = 'sof_already_set'


class SOFSetAllFieldsRequiredError(BaseError):
    default_detail = _('You must set all fields.')
    default_code = 'sof_all_fields_required'


class BadSecret(BaseError):
    default_detail = _('Bad secret')
    default_code = 'bad_secret'


class PartnerPlatformBlockUserError(BaseError):
    default_detail = _('User block.')
    default_code = 'account_block'


class Wrong2FATooManyTimes(BaseError):
    default_detail = _('Wrong input 2fa code too many times. Please login again.')
    default_code = 'wrong_2fa_many_times'


class MaxCaptchaSkipAttempts(Exception):
    pass


class SmsSendingError(BaseError):
    default_detail = _('SMS sending error')
    default_code = 'sms_sending_error'


class AccountNotActive(ValidationError):
    pass


class TwoFAFailed(BaseError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _('You do not have permission to perform this action.')
    default_code = '2fa_failed'
