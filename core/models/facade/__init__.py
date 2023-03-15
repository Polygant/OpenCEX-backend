import binascii
import datetime
import logging
import os
from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields.jsonb import JSONField
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.transaction import atomic
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from core.cache import facade_cache, COINS_STATIC_DATA_CACHE_KEY
from core.consts.orders import BUY
from core.consts.orders import EXCHANGE
from core.currency import CurrencyModelField
from core.enums.profile import UserTypeEnum
from core.exceptions.facade import BadSecret
from core.models.inouts.fees_and_limits import FeesAndLimits
from exchange.loggers import DynamicFieldFilter
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.cache import PrefixedRedisCache
from lib.fields import MoneyField, RichTextField
from lib.utils import hmac_random_string, generate_random_string

EXPIRE_TOKEN_CACHE = PrefixedRedisCache.get_cache(prefix='expire_token')


# auth_log = logging.getLogger('graypy')
auth_log = logging.getLogger('auth' + __name__)
auth_log.addFilter(DynamicFieldFilter())


def generate_remittance_id():
    return generate_random_string(length=12).upper()


class Profile(BaseModel):

    INTERFACE_ADVANCED = 'advance'
    INTERFACE_SIMPLE = 'simple'

    INTERFACE_TYPES = (
        (INTERFACE_ADVANCED, _('Advance')),
        (INTERFACE_SIMPLE, _('Simple'))
    )

    USER_TYPE_DEFAULT = UserTypeEnum.user.value
    USER_TYPE_STAFF = UserTypeEnum.staff.value
    USER_TYPE_BOT = UserTypeEnum.bot.value

    USER_TYPES = UserTypeEnum.choices()

    user_type = models.IntegerField(default=USER_TYPE_DEFAULT, choices=USER_TYPES)

    user = models.OneToOneField(to=settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE, unique=True, related_name='profile')
    auto_logout_timeout = models.IntegerField(default=1440)
    payouts_freezed_till = models.DateTimeField(default=None, null=True, blank=True)
    api_key = models.CharField(max_length=64, default=hmac_random_string)
    secret_key = models.CharField(max_length=64, default=hmac_random_string)
    api_callback_url = models.URLField(max_length=255, null=True, blank=True)
    birth_day = models.DateTimeField(default=None, null=True, blank=True)
    country = CountryField(default=None, null=True, blank=True, blank_label='Not specified')
    register_ip = models.GenericIPAddressField(null=True, blank=True)
    interface = models.CharField(max_length=64, default=None, null=True,
                                 blank=True, choices=INTERFACE_TYPES)
    phone = models.CharField(max_length=64, default=None, null=True, blank=True)
    is_sof_verified = models.BooleanField(default=False)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)
    sepa_remittance_id = models.CharField(
        unique=True, max_length=12, default=generate_remittance_id)
    is_auto_orders_enabled = models.BooleanField(default=False)
    email_ip_changed = models.BooleanField(default=False)
    email_failed_login = models.BooleanField(default=True)
    withdrawals_sms_confirmation = models.BooleanField(default=False)

    def set_payouts_freeze(self, minutes):
        self.payouts_freezed_till = now() + datetime.timedelta(minutes=minutes)
        self.save()

    def is_payouts_freezed(self):
        return self.payouts_freezed_till and self.payouts_freezed_till > now()

    def regenerate_keys(self):
        """ Генерация api и secret ключей"""
        self.secret_key = hmac_random_string()
        self.api_key = hmac_random_string()
        self.save()

    def get_fee(self, order):
        return self.get_fee_by_user(self.user_id, order)

    @classmethod
    def get_fee_by_user(cls, user_id, order):
        cache_key = f'{user_id}-{order.type}'
        cache_val = facade_cache.get(cache_key)
        if cache_val is not None:
            return cache_val

        if order.type == EXCHANGE:
            user_exchange_fee = UserExchangeFee.objects.filter(user_id=user_id).first()
            if user_exchange_fee and user_exchange_fee.fee_rate is not None:
                result = user_exchange_fee.fee_rate
            else:
                result = FeesAndLimits.get_fee(
                    order.pair.base.code,
                    FeesAndLimits.EXCHANGE,
                    FeesAndLimits.VALUE
                )
        # elif order.type == MARKET:
        #     user_fee = UserMarketFee.objects.filter(user_id=user_id).first()
        #     if user_fee:
        #         result = user_fee.fee_rate
        else:
            user_fee = UserFee.objects.filter(user_id=user_id).first()
            if user_fee and user_fee.fee_rate is not None:
                result = user_fee.fee_rate
            else:
                currency = order.pair.base.code if order.operation == BUY else order.pair.quote.code
                result = FeesAndLimits.get_fee(
                    currency,
                    FeesAndLimits.ORDER,
                    FeesAndLimits.LIMIT_ORDER
                )

        facade_cache.set(cache_key, result, timeout=60*5)

        return result

    def drop_sms(self):
        with atomic():
            self.withdrawals_sms_confirmation = False
            self.set_payouts_freeze(60 * 24 * 3)
            SmsHistory.objects.create(
                user=self.user,
                withdrawals_sms_confirmation=False,
                phone=self.phone
            )


class UserFee(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    user = models.OneToOneField(to=settings.AUTH_USER_MODEL,
                                on_delete=models.DO_NOTHING, unique=True)
    fee_rate = MoneyField(null=True, blank=True, default=0.001)

    def __str__(self, *args, **kwargs):
        return '{} {}'.format(self.user.email, self.fee_rate)


class UserExchangeFee(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    user = models.OneToOneField(to=settings.AUTH_USER_MODEL,
                                on_delete=models.DO_NOTHING, unique=True)
    fee_rate = MoneyField(null=True, blank=True, default=0.002)

    def __str__(self, *args, **kwargs):
        return '{} {}'.format(self.user.email, self.fee_rate)


class TwoFactorSecretTokens(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    secret = models.CharField(default=None, max_length=200, null=True, blank=True)

    @classmethod
    def is_enabled_for_user(cls, usr):
        usr = cls.ensure_user(usr)
        if not usr:
            return False
        return bool(cls.objects.get(user=usr).secret)

    @staticmethod
    def ensure_user(usr_or_name):
        if isinstance(usr_or_name, str):
            return User.objects.filter(username__iexact=usr_or_name).first()
        elif isinstance(usr_or_name, User):
            return usr_or_name
        else:
            # TODO error_format
            raise ValueError(usr_or_name)

    @classmethod
    def set_code(cls, usr, code):
        assert isinstance(code, str) and code
        instance = cls.objects.filter(user=usr).first()
        if not instance:
            return
        instance.secret = code
        instance.save()
        fields = {
            'user': usr,
            'Systemd_unit': '2fa_enabled'
        }

        DynamicFieldFilter.set_fields(fields)
        auth_log.info(
            '[2fa enabled] user: %s',
            usr,
        )
        TwoFactorSecretHistory(user=usr, status=True).save()

    def drop(self):
        self.secret = None
        self.save()
        TwoFactorSecretHistory(user=self.user, status=False).save()

    @classmethod
    def disable(cls, usr, code):
        if not cls.check_g_code(usr, code):
            raise BadSecret('bad secret')
        else:
            instance = cls.objects.filter(user=usr).first()
            if not instance:
                return

            instance.drop()

            fields = {
                'user': usr,
                'Systemd_unit': '2fa_disabled'
            }

            DynamicFieldFilter.set_fields(fields)
            auth_log.info(
                '[2fa disabled] user: %s',
                usr,
            )

    @classmethod
    def drop_for_user(cls, usr):
        instance = cls.objects.filter(user=usr).first()
        if not instance:
            return
        instance.drop()

    @classmethod
    def check_g_code(cls, user, googlecode):
        user = cls.ensure_user(user)
        if not user:
            return True
        secret = cls.objects.get(user=user).secret
        if secret:
            totp = pyotp.TOTP(secret)
            result = cls.check_totp(totp, googlecode)
            if result is False:
                fields = {
                    'user': user,
                    'Systemd_unit': '2fa_check_failed'
                }

                DynamicFieldFilter.set_fields(fields)
                auth_log.error(
                    '[2fa check failed] user: %s',
                    user,
                )
            return result

        return True

    @classmethod
    def check_g_otp(cls, secret, code):
        totp = pyotp.TOTP(secret)
        return cls.check_totp(totp, code)

    @classmethod
    def check_totp(cls, totp, code) -> bool:
        """
        Check if code valid for current or previous time window
        """
        current_otp = totp.now()
        previous_otp = totp.at(now(), counter_offset=-1)

        return code in [current_otp, previous_otp]

    @classmethod
    def generate_secret(cls):
        return pyotp.random_base32()


class Message(BaseModel, UserMixinModel):  # TODO: move outside db to mongo?
    subject = models.CharField(max_length=200)
    content = models.CharField(max_length=1000)
    read = models.BooleanField(default=False)


class TwoFactorSecretHistory(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.BooleanField(default=True)


class UserKYC(models.Model):

    ANSWER_GREEN = 'GREEN'
    ANSWER_RED = 'RED'

    ANSWERS = (
        (ANSWER_GREEN, _('Green')),
        (ANSWER_RED, _('Red')),
    )

    REJECT_TYPE_FINAL = 'FINAL'
    REJECT_TYPE_RETRY = 'RETRY'
    REJECT_TYPE_EXTERNAL = 'EXTERNAL'

    REJECT_TYPES = (
        (REJECT_TYPE_FINAL, _('Final')),
        (REJECT_TYPE_RETRY, _('Retry')),
        (REJECT_TYPE_EXTERNAL, _('External')),
    )

    created = models.DateTimeField(auto_now_add=True)
    user = models.OneToOneField(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE, unique=True)
    applicantId = models.CharField(max_length=200, default='', blank=True)
    reviewAnswer = models.CharField(max_length=200, default='', blank=True)
    kyc_data = JSONField(default=dict, blank=True)
    last_kyc_data_update = models.DateTimeField(null=True, blank=True)
    # force approve without real check
    forced_approve = models.BooleanField(default=False)
    rejectType = models.CharField(max_length=255, default=None, null=True, choices=REJECT_TYPES)
    moderationComment = models.CharField(max_length=250, null=True, blank=True)
    rejectLabels = ArrayField(
        models.CharField(max_length=250, null=True, blank=True),
        null=True,
        blank=True,
    )

    def valid(self) -> bool:
        """
        Check if answer is GREEN or force approved by moder
        """
        is_green_answer = self.reviewAnswer.lower() == self.ANSWER_GREEN.lower()
        return is_green_answer or self.forced_approve

    @classmethod
    def for_user(cls, user):
        try:
            return cls.objects.get(user=user).reviewAnswer
        except ObjectDoesNotExist:
            return None

    @classmethod
    def valid_for_user(cls, user) -> bool:
        kyc = cls.objects.filter(user=user).first()
        if kyc is None:
            return False
        return kyc.valid()

    @classmethod
    def status_for_user(cls, user):
        kyc = cls.objects.filter(user=user).first()
        if not kyc:
            return 'no'
        if kyc.forced_approve or kyc.reviewAnswer == UserKYC.ANSWER_GREEN:
            return 'green'
        elif kyc.reviewAnswer == UserKYC.ANSWER_RED:
            status = 'red'
            if kyc.rejectType:
                status += f'-{kyc.rejectType.lower()}'
            return status
        else:
            return 'no'

    def __str__(self):
        return f'<{self.user}>: {self.reviewAnswer} data:{bool(self.kyc_data)}'

    # todo: remove unused
    @property
    def current_kyc_data(self):
        if not self.kyc_data:
            return None

        item = self.kyc_data['list']['items'][0]
        result = {}
        result.update(item['info'])
        return result


class SourceOfFunds(models.Model):
    PROFESSION_PRIVATE_COMPANY_EMPLOYEE = 1
    PROFESSION_STATE_EMPLOYEE = 2
    PROFESSION_BUSINESS_OWNER = 3
    PROFESSION_PROFESSIONAL = 4
    PROFESSION_AGRICULTURIST = 5
    PROFESSION_RETIRED = 6
    PROFESSION_HOUSEWIFE = 7
    PROFESSION_STUDENT = 8
    PROFESSION_TRADER = 9

    PROFESSIONS = (
        (PROFESSION_PRIVATE_COMPANY_EMPLOYEE, _('Private company employee')),
        (PROFESSION_STATE_EMPLOYEE, _('State employee')),
        (PROFESSION_BUSINESS_OWNER, _('Business owner')),
        (PROFESSION_PROFESSIONAL, _('Professional')),
        (PROFESSION_AGRICULTURIST, _('Agriculturist')),
        (PROFESSION_RETIRED, _('Retired')),
        (PROFESSION_HOUSEWIFE, _('Housewife')),
        (PROFESSION_STUDENT, _('Student')),
        (PROFESSION_TRADER, _('Trader')),
    )

    SOURCE_EMPLOYMENT_INCOME = 1
    SOURCE_SAVINGS = 2
    SOURCE_PROPERTY_SALE = 3
    SOURCE_SALE_OF_SHARES = 4
    SOURCE_LOAN = 5
    SOURCE_COMPANY_SALE = 6
    SOURCE_COMPANY_PROFITS = 7

    SOURCES = (
        (SOURCE_EMPLOYMENT_INCOME, _('Employment Income')),
        (SOURCE_SAVINGS, _('Savings / deposits')),
        (SOURCE_PROPERTY_SALE, _('Property Sale')),
        (SOURCE_SALE_OF_SHARES, _('Sale of shares or other investment')),
        (SOURCE_LOAN, _('Loan')),
        (SOURCE_COMPANY_SALE, _('Company Sale')),
        (SOURCE_COMPANY_PROFITS, _('Company Profits / Dividends')),
    )

    user = models.OneToOneField(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_beneficiary = models.NullBooleanField()
    profession = ArrayField(
        models.PositiveSmallIntegerField(choices=PROFESSIONS, blank=True, null=True),
        blank=True,
        null=True,
    )
    source = ArrayField(
        models.PositiveSmallIntegerField(choices=SOURCES, blank=True, null=True),
        blank=True,
        null=True,
    )

    @classmethod
    def get_by_user(cls, user):
        return cls.objects.filter(user=user).first()

    def is_set(self) -> bool:
        """
        Is data already saved?
        """
        return bool(self.profession and self.source)

    def __str__(self):
        return (f'{self.user.username}')


class ExpiringToken(models.Model):
    """
    The default authorization token model.
    """
    key = models.CharField(("Key"), max_length=40, primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name='facade_auth_token',
        on_delete=models.CASCADE, verbose_name=("User")
    )
    created = models.DateTimeField(("Created"), auto_now_add=True)
    last_used = models.DateTimeField(auto_now_add=True)

    def expired(self):
        now = timezone.now()
        user_timeout = self.user.profile.auto_logout_timeout
        last_used = EXPIRE_TOKEN_CACHE.get(
            self.key, self.created.timestamp() + timedelta(minutes=user_timeout).total_seconds()
        )
        if last_used < now.timestamp() - timedelta(minutes=user_timeout).total_seconds():
            return True
        EXPIRE_TOKEN_CACHE.set(
            self.key, now.timestamp(), timeout=timedelta(minutes=user_timeout).total_seconds() + 5 * 60
        )
        return False

    class Meta:
        # Work around for a bug in Django:
        # https://code.djangoproject.com/ticket/19422
        #
        # Also see corresponding ticket:
        # https://github.com/encode/django-rest-framework/issues/705
        verbose_name = "Token"
        verbose_name_plural = "Tokens"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ExpiringToken, self).save(*args, **kwargs)

    def generate_key(self):
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return self.user.email


class LoginHistory(BaseModel, UserMixinModel):
    user_agent = models.CharField(max_length=255)
    ip = models.CharField(max_length=100)


class AccessLog(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    ip = models.CharField(max_length=64, default='')
    username = models.CharField(max_length=256, default='')
    method = models.CharField(max_length=20, default='')
    uri = models.TextField(default='')
    referer = models.TextField(default='')
    status = models.CharField(max_length=3, default='200')
    user_agent = models.TextField(default='')


class SmsHistory(UserMixinModel):
    created = models.DateTimeField(auto_now_add=True)
    phone = models.CharField(max_length=64, default=None, null=True, blank=True)
    withdrawals_sms_confirmation = models.BooleanField(default=False)


class SmsConfirmationHistory(UserMixinModel):
    ACTION_TYPE_SEND_SMS = 1
    ACTION_TYPE_VERIFY_CODE = 2

    VERIFICATION_TYPE_WITHDRAWAL = 1
    VERIFICATION_TYPE_PHONE = 2
    VERIFICATION_TYPE_DISABLE_SMS = 3

    ACTION_TYPES = (
        (ACTION_TYPE_SEND_SMS, 'Send SMS'),
        (ACTION_TYPE_VERIFY_CODE, 'Verify Code'),
    )

    VERIFICATION_TYPES = (
        (VERIFICATION_TYPE_WITHDRAWAL, 'Withdrawal'),
        (VERIFICATION_TYPE_PHONE, 'Phone'),
        (VERIFICATION_TYPE_DISABLE_SMS, 'Disable sms'),
    )

    created = models.DateTimeField(auto_now_add=True)
    phone = models.CharField(max_length=64)
    action_type = models.PositiveSmallIntegerField(choices=ACTION_TYPES)
    verification_type = models.PositiveSmallIntegerField(choices=VERIFICATION_TYPES)
    is_success = models.BooleanField(default=False)
    code = models.CharField(max_length=8, null=True, blank=True)

    def success(self):
        self.is_success = True
        self.save()


class UserRestrictions(BaseModel):
    user = models.OneToOneField(to=settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE, unique=True, related_name='restrictions')
    disable_topups = models.BooleanField(default=False)
    disable_withdrawals = models.BooleanField(default=False)
    disable_orders = models.BooleanField(default=False)


def default_coin_info_links():
    return {
        'bt': {
            'title': 'BitcoinTalk',
            'href': ''
        },
        'official': {
            'title': '',
            'href': ''
        },
        'cmc': {
            'title': 'CoinMarketCap',
            'href': ''
        },
        'exp': {
            'title': 'Explorer',
            'href': ''
        },
    }


class CoinInfo(models.Model):
    currency = CurrencyModelField(unique=True)
    name = models.CharField(max_length=255)
    is_base = models.BooleanField(default=False)
    decimals = models.PositiveSmallIntegerField(default=8)
    index = models.SmallIntegerField()
    tx_explorer = models.CharField(max_length=255, default='')
    links = models.JSONField(default=default_coin_info_links)

    def as_dict(self):
        from core.models import DisabledCoin
        blockchain_list = [
            b for b in self.currency.blockchain_list if not DisabledCoin.is_coin_disabled(b, DisabledCoin.DISABLE_ALL)
        ]

        return {
            'name': self.name,
            'base': self.is_base,
            'decimals': self.decimals,
            'index': self.index,
            'tx_explorer': self.tx_explorer,
            'links': self.links,
            'is_token': self.currency.is_token,
            'blockchain_list': blockchain_list,
        }

    def save(self, *args, **kwargs):
        super(CoinInfo, self).save(*args, **kwargs)
        self._cache_data(True)

    @classmethod
    def get_coins_info(cls, update=False) -> dict:
        return cls._cache_data(update)

    @classmethod
    def _cache_data(cls, set_cache=False):
        data = cache.get(COINS_STATIC_DATA_CACHE_KEY, {})
        if set_cache or not data:
            for coin in cls.objects.all():
                data[coin.currency.code] = coin.as_dict()
            cache.set(COINS_STATIC_DATA_CACHE_KEY, data)
        return data

