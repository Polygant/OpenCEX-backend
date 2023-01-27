import logging
import string

from django.conf import settings
from twilio.rest import Client

from core.exceptions.facade import SmsSendingError
from core.models.facade import SmsConfirmationHistory
from lib.cache import PrefixedRedisCache
from lib.utils import generate_random_string

log = logging.getLogger(__name__)
cache = PrefixedRedisCache.get_cache(prefix='twillio-app-cache-')


class TwilioClient:
    _twilio = None
    _from = None

    TYPE_WITHDRAWAL = 'withdrawal'
    TYPE_PHONE = 'phone'
    TYPE_DISABLE_SMS = 'disable_sms_withdrawals'

    IS_ENABLED = settings.IS_SMS_ENABLED and settings.TWILIO['ENABLED']

    VERIFICATION_TYPES = [TYPE_PHONE, TYPE_WITHDRAWAL, TYPE_DISABLE_SMS]

    def __init__(self, account_sid, auth_token, phone_from, ) -> None:
        if self.IS_ENABLED:
            self._twilio = Client(account_sid, auth_token)
        self._from = phone_from

    def verify_sms(self, phone, verification_type):

        if not self.IS_ENABLED:
            return True

        cache_code_key = f'{verification_type}-code-{phone}'
        key = generate_random_string(6, string.digits)

        try:
            message = self._twilio.messages.create(
                body='Verify code: ' + key,
                from_=self._from,
                to=phone
            )
        except Exception:
            log.exception('Cant send sms')
            raise SmsSendingError()

        if message.status in ['pending', 'queued']:
            cache.set(cache_code_key, key, timeout=60 * 2)
            return True

        return False

    def check_code(self, phone, code, verification_type):
        if not self.IS_ENABLED:
            return True

        cache_key = f'{verification_type}-code-{phone}'
        cache_val = cache.get(cache_key)

        if cache_val and cache_val == code:
            return True

        return False

    @classmethod
    def verification_type_to_int(cls, verification_type):
        if verification_type == cls.TYPE_WITHDRAWAL:
            return SmsConfirmationHistory.VERIFICATION_TYPE_WITHDRAWAL
        if verification_type == cls.TYPE_PHONE:
            return SmsConfirmationHistory.VERIFICATION_TYPE_PHONE
        if verification_type == cls.TYPE_DISABLE_SMS:
            return SmsConfirmationHistory.VERIFICATION_TYPE_DISABLE_SMS


twilio_client = TwilioClient(
    account_sid=settings.TWILIO['ACCOUNT_SID'],
    auth_token=settings.TWILIO['AUTH_TOKEN'],
    phone_from=settings.TWILIO['PHONE_FROM'],
)
