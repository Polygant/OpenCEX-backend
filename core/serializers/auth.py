import logging
import re

import requests
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Model
from django.db.transaction import atomic
from django.utils.translation import ugettext_lazy as _
from django_countries import countries
from django_countries.serializer_fields import CountryField
from django_user_agents.utils import get_user_agent
from ipware import get_client_ip
from rest_auth.registration.serializers import RegisterSerializer as BaseRegisterSerializer
from rest_auth.serializers import LoginSerializer as BaseLoginSerializer
from rest_auth.serializers import PasswordChangeSerializer as BasePasswordChangeSerializer
from rest_auth.serializers import PasswordResetConfirmSerializer as BasePasswordResetConfirmSerializer
from rest_auth.serializers import PasswordResetSerializer as BasePasswordResetSerializer
from rest_auth.serializers import UserDetailsSerializer
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer
from user_agents.parsers import UserAgent

from core.cache import RESEND_VERIFICATION_TOKEN_CACHE_KEY, RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY
from core.exceptions.facade import TwoFAFailed, MaxCaptchaSkipAttempts, Wrong2FATooManyTimes, AccountNotActive
from core.models.facade import LoginHistory
from core.models.facade import TwoFactorSecretTokens
from core.models.facade import UserExchangeFee
from core.models.facade import UserFee, Profile
from core.models.facade import UserKYC
from core.tasks.facade import notify_failed_login
from core.tasks.facade import notify_user_ip_changed
from core.utils.auth import RegisterUserCheck
from exchange.loggers import DynamicFieldFilter
from lib.serializers import LANG_FIELD
from lib.utils import generate_random_string

log = logging.getLogger(__name__)
# auth_log = logging.getLogger('graypy')
auth_log = logging.getLogger('auth' + __name__)
auth_log.addFilter(DynamicFieldFilter())

UserModel: Model = get_user_model()


class BadInvite(APIException):
    default_detail = 'BadInvite'
    default_code = 400


class UserSerializer(UserDetailsSerializer):
    user_fee = serializers.SerializerMethodField()
    user_exchange_fee = serializers.SerializerMethodField()

    class Meta(UserDetailsSerializer.Meta):
        fields = ('username', 'first_name', 'last_name', 'user_fee', 'user_exchange_fee')

    def get_user_fee(self, obj):
        user_fee = UserFee.objects.filter(user_id=obj.id).first()
        if user_fee and user_fee.fee_rate:
            return user_fee.fee_rate
        return 0

    def get_user_exchange_fee(self, obj):
        user_exchange_fee = UserExchangeFee.objects.filter(user_id=obj.id).first()
        if user_exchange_fee and user_exchange_fee.fee_rate:
            return user_exchange_fee.fee_rate
        return 0

    def update(self, instance, validated_data):
        instance = super(UserSerializer, self).update(instance, validated_data)
        return instance

    def create(self, *args, **kwargs):
        raise MethodNotAllowed('create')


class GCodeMixIn(serializers.Serializer):
    googlecode = serializers.CharField(required=False, allow_blank=True)

    def check_2fa_for_user(self, username, gcode):
        if not TwoFactorSecretTokens.check_g_code(username, gcode):
            raise TwoFAFailed()


class CaptchaProcessor:
    CAPTCHA_ENABLED = settings.CAPTCHA_ENABLED
    PASSED_PREFIX = 'passed:'
    MAX_ERROR_ATTEMPTS = 6
    CACHE_TIMEOUT = settings.CAPTCHA_TIMEOUT

    def __init__(self, uid, ip, captcha_response, skip_extra_checks=False):
        self.uid = uid
        self.ip = ip
        self.captcha_response = captcha_response
        self.skip_extra_checks = skip_extra_checks

    def get_ckey(self):
        return f'{self.uid}{self.ip}'

    @classmethod
    def cache_key(cls, value):
        return f'{cls.PASSED_PREFIX}{value}'

    @classmethod
    def get_cache(cls, key):
        ckey = cls.cache_key(key)
        data = cache.get(ckey)
        return data

    @classmethod
    def get_cache_ttl(cls, key):
        ckey = cls.cache_key(key)
        return cache.ttl(ckey)

    @classmethod
    def del_cache(cls, key):
        ckey = cls.cache_key(key)
        cache.delete(ckey)

    @classmethod
    def set_cache(cls, key, timeout=None, data=None):
        ckey = cls.cache_key(key)
        if data is None:
            data = cls.MAX_ERROR_ATTEMPTS
        cache.set(ckey, data, timeout or cls.CACHE_TIMEOUT)

    def is_captcha_required(self):
        if self.ip in ['127.0.0.1', 'localhost'] or (self.ip and re.match(settings.CAPTCHA_ALLOWED_IP_MASK, self.ip)):
            return False

        if self.is_captcha_passed():
            return False
        return True
        # if self.is_captcha_passed():
        #     # disabled for timeout
        #     return False
        #
        # if not self.ip:
        #     return True
        #
        # # disable captcha for internal api calls from bots
        # if BOT_USERNAME_CMPRE.match(self.uid) and self.ip in self.allowed_hosts():
        #     return False
        #
        # if self.get_cache(self.ip):
        #     return True
        #
        # if self.get_cache(self.uid):
        #     return True
        #
        # return False

    def check(self):
        if not self.CAPTCHA_ENABLED:
            return

        if not self.skip_extra_checks:
            if not self.is_captcha_required():
                return

        if not self.captcha_response or self.captcha_response == '':
            raise ValidationError({
                'message': 'invalidate data',
                'type': 'captcha_required'
            })
        try:
            self._captcha_check(self.captcha_response)
        except Exception:
            self.del_captcha_pass()
            raise


    @classmethod
    def _captcha_check(cls, response, secret=settings.RECAPTCHA_SECRET):
        r = requests.post('https://www.google.com/recaptcha/api/siteverify',
                          data={'secret': secret, 'response': response})
        if not r.json()['success']:
            raise ValidationError({
                'message': 'bad captcha!',
                'type': 'bad_captcha'
            })

    def decrease_attempts(self, custom_exception=None):
        data = self.get_cache(self.get_ckey())
        if data is not None:
            ttl = self.get_cache_ttl(self.get_ckey())
            data -= 1
            if data <= 0:
                self.del_captcha_pass()
                if custom_exception:
                    raise custom_exception()
                raise MaxCaptchaSkipAttempts()
            else:
                self.set_cache(self.get_ckey(), data=data, timeout=ttl)

    def del_captcha_pass(self):
        self.del_cache(self.get_ckey())

    def set_captcha_passed(self):
        if not self.is_captcha_passed():
            self.set_cache(self.get_ckey(), timeout=180)

    def is_captcha_passed(self):
        return bool(self.get_cache(self.get_ckey()))


class LoginSerializer(GCodeMixIn, BaseLoginSerializer):
    captcha = serializers.CharField(required=False, allow_blank=True)
    username = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self._context['request']
        ip = get_client_ip(self._context['request'])[0]
        if request.META.get('HTTP_CF_CONNECTING_IP'):
            ip = request.META.get('HTTP_CF_CONNECTING_IP')
        username = (attrs.get('email') or attrs.get('username')).lower()
        password = attrs.get('password')
        captcher = CaptchaProcessor(
            username,
            ip,
            attrs.get('captcha'),
        )
        captcher.check()
        user_agent: UserAgent = get_user_agent(request)
        fields = {
            'user': username,
            'ip': ip,
            'browser': f'({user_agent.browser.family} {user_agent.browser.version_string})',
            'os': f'({user_agent.os.family} {user_agent.os.version_string})',
            'device': user_agent.device.family,
        }

        try:
            user = self._validate_username(username, password)
            # Did we get back an active user?
            if not user:
                msg = _('Unable to log in with provided credentials.')
                raise ValidationError(
                    {
                        'message': msg,
                        'type': 'wrong_data'
                    }
                )

            if not user.is_active:
                msg = _('User account is disabled.')
                raise AccountNotActive(
                    {
                        'message': msg,
                        'type': 'account_block'
                    }
                )

            email_address = user.emailaddress_set.get(email=user.email)
            if not email_address.verified:
                current_token = cache.get(f'{RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY}{user.id}')
                if not current_token:
                    current_token = generate_random_string(32)
                    cache.set(f'{RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY}{user.id}', current_token, timeout=1800)
                    cache.set(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{current_token}', user.id, timeout=1800)
                raise AccountNotActive({
                    'error': 'email_not_verified',
                    'type': 'email_not_verified',
                    'token': current_token
                })

            attrs['user'] = user
            captcher.set_captcha_passed()

        except AccountNotActive:
            #  do not send email
            captcher.del_captcha_pass()
            raise

        except Exception as exc_ch:
            captcher.del_captcha_pass()
            fields['Systemd_unit'] = 'failed_auth'
            DynamicFieldFilter.set_fields(fields)
            auth_log.error(
                '[User auth failed] user: %s,  ip: %s, browser: %s, os: %s, device: %s',
                username,
                ip,
                fields['browser'],
                fields['os'],
                fields['device'],
            )

            user = UserModel.objects.filter(username=username).first()

            if user and user.profile.email_failed_login:
                notify_failed_login.apply_async([user.id])
            raise exc_ch

        try:
            self.check_2fa_for_user(attrs['user'], attrs.get('googlecode', None))
        except TwoFAFailed:
            captcher.decrease_attempts(Wrong2FATooManyTimes)
            raise

        captcher.del_captcha_pass()

        if user.profile.email_ip_changed:
            ip_history = list(LoginHistory.objects.filter(user=user).values_list('ip', flat=True))
            if ip_history and ip not in ip_history:
                notify_user_ip_changed.apply_async([user.id, ip])

        LoginHistory(
            user=user,
            ip=ip,
            user_agent=user_agent.ua_string[:255]
        ).save()

        fields['Systemd_unit'] = 'auth'
        DynamicFieldFilter.set_fields(fields)
        auth_log.info(
            '[User auth success] user: %s,  ip: %s, browser: %s, os: %s, device: %s',
            attrs['user'],
            ip,
            fields['browser'],
            fields['os'],
            fields['device'],
        )

        return attrs


class RegisterSerializer(BaseRegisterSerializer):
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    captchaResponse = serializers.CharField(required=True, allow_blank=True)
    country = CountryField()
    email = serializers.EmailField(required=False)
    username = serializers.EmailField(required=True)
    invite_code = serializers.CharField(required=False)
    lang = LANG_FIELD

    def validate_username(self, username):
        if not RegisterUserCheck.validate_score_email(username):
            raise ValidationError({
                'message': _('similar username was recently used'),
                'type': 'registration_similar_username'
            })
        return BaseRegisterSerializer.validate_email(self, username)

    def validate(self, data):
        if settings.DISABLE_REGISTRATION:
            raise ValidationError({
                'message': 'Registration is disabled',
                'type': 'registration_disable'
            })

        username = (data.get('email') or data.get('username')).lower()
        captcher = CaptchaProcessor(
            username,
            None,
            data.get('captchaResponse'),
            skip_extra_checks=True,
        )
        captcher.check()

        data['email'] = username
        data['username'] = username
        data = super(RegisterSerializer, self).validate(data)

        country = data.get('country')
        if not country:
            # TODO errors
            raise ValidationError({
                    'message': _('Country required!'),
                    'type': 'country_required'
                })

        if country in settings.DISALLOW_COUNTRY:
            # TODO errors
            raise ValidationError({
                    'message': _('Country not supported!'),
                    'type': 'country_not_support'
                })

        if not countries.countries.get(country):
            # TODO errors
            raise ValidationError({
                    'message': _('Incorrect country!'),
                    'type': 'country_incorrect'
                })

        if 'invite_code' in data:
            del data['invite_code']
        return data

    def get_cleaned_data(self):
        return {
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'username': self.validated_data.get('username', ''),
            'password1': self.validated_data.get('password1', ''),
            'email': self.validated_data.get('email', '')
        }

    def _save(self, request):
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        adapter.save_user(request, user, self)
        self.custom_signup(request, user)
        setup_user_email(request, user, [])
        return user

    def save(self, request):
        request._request.lang = self.validated_data.get('lang', 'en')
        with atomic():
            user = self._save(request)
            user.profile.country = request.data.get('country')
            user.profile.birth_day = request.data.get('birth_day')
            user.profile.register_ip = next(iter(get_client_ip(request) or []), None)
            user.profile.save()

        RegisterUserCheck.update_last_emails()
        return user


class PasswdChangeSerializer(GCodeMixIn, BasePasswordChangeSerializer):

    def validate_old_password(self, value):
        invalid_password_conditions = (
            self.old_password_field_enabled,
            self.user,
            not self.user.check_password(value)
        )

        if all(invalid_password_conditions):
            raise serializers.ValidationError({
                'msg': 'Invalid password',
                'type': 'invalid_password',
            })
        return value

    def validate(self, attrs):
        try:
            attrs = BasePasswordChangeSerializer.validate(self, attrs)
        except ValidationError as e:
            fields = {
                'Systemd_unit': 'password_change_failed',
                'user': self.user
            }
            DynamicFieldFilter.set_fields(fields)
            auth_log.error(
                '[password change failed] user: %s',
                self.user,
            )
            raise e

        self.check_2fa_for_user(self.user.username, attrs.get('googlecode', None))

        fields = {
            'Systemd_unit': 'password_change_success',
            'user': self.user
        }
        DynamicFieldFilter.set_fields(fields)
        auth_log.info(
            '[password change success] user: %s',
            self.user,
        )
        return attrs


class PasswordResetSerializer(GCodeMixIn, BasePasswordResetSerializer):
    lang = LANG_FIELD
    captcha = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = BasePasswordResetSerializer.validate(self, attrs)
        # self.check_2fa_for_user(attrs['email'], attrs.get('googlecode', None))

        # request = self.context.get('request')
        captcher = CaptchaProcessor(
            attrs.get('email').lower(),
            None,
            attrs.get('captcha'),
            skip_extra_checks=True,
        )
        captcher.check()

        fields = {
            'Systemd_unit': 'password_reset',
            'email': attrs['email']
        }
        DynamicFieldFilter.set_fields(fields)
        auth_log.info(
            '[password reset request] email: %s',
            attrs['email'],
        )
        return attrs

    def get_email_options(self):
        return dict(subject_template_name='account/email/password_reset_key_subject.txt',
                    email_template_name='account/email/password_reset_key_message.txt',
                    extra_email_context={"lang": self.validated_data.get('lang', 'en')}
                    )


class PasswordResetConfirmSerializer(BasePasswordResetConfirmSerializer):
    def save(self):
        ret = BasePasswordResetConfirmSerializer.save(self)
        self.user.profile.set_payouts_freeze(settings.PAYOUTS_FREEZE_ON_PWD_RESET)

        fields = {
            'Systemd_unit': 'password_reset_confirm',
            'user': self.user
        }
        DynamicFieldFilter.set_fields(fields)
        auth_log.info(
            '[password reset confirm] user: %s',
            self.user,
        )
        return ret


class UserProfileSerializer(ModelSerializer):
    auto_logout_timeout = serializers.IntegerField(min_value=60, required=False)
    user = UserSerializer(many=False, read_only=True)
    country = CountryField(country_dict=True, read_only=True, required=False)
    birthday = serializers.DateTimeField(source='birth_day', read_only=True, required=False)
    kyc_status = serializers.SerializerMethodField()
    kyc_enabled = serializers.SerializerMethodField()
    kyt_enabled = serializers.SerializerMethodField()
    sms_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            'user',
            'auto_logout_timeout',
            'interface',
            'phone',
            'country',
            'birthday',
            'is_sof_verified',
            'language',
            'sepa_remittance_id',
            'is_auto_orders_enabled',
            'email_ip_changed',
            'email_failed_login',
            'withdrawals_sms_confirmation',
            'kyc_status',
            'kyc_enabled',
            'kyt_enabled',
            'sms_enabled',
        )
        read_only_fields = (
            'user',
            'phone',
            'is_sof_verified',
            'sepa_remittance_id',
            'is_auto_orders_enabled',
            'withdrawals_sms_confirmation',
            'kyc_status',
            'kyc_enabled',
            'kyt_enabled',
            'sms_enabled',
        )

    def get_kyc_status(self, obj):
        return UserKYC.status_for_user(obj.user)

    def get_kyt_enabled(self, obj):
        return settings.IS_KYT_ENABLED

    def get_kyc_enabled(self, obj):
        return settings.IS_KYC_ENABLED

    def get_sms_enabled(self, obj):
        return settings.IS_SMS_ENABLED


# class TokenSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ExpiringToken
#         fields = ('key',)


class OurJWTSerializer(serializers.Serializer):
    """
    Serializer for JWT authentication.
    """
    key = serializers.SerializerMethodField()

    def get_key(self, obj):
        from rest_framework_jwt.settings import api_settings

        # @see exchange/settings/rest.py:JWT_AUTH  or rest_framework_jwt.utils.jwt_payload_handler
        jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER

        # @see exchange/settings/rest.py:JWT_AUTH  or rest_framework_jwt.utils.jwt_encode_handler
        jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER
        payload = jwt_payload_handler(obj['user'])
        return jwt_encode_handler(payload)
