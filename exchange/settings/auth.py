# REST_AUTH_TOKEN_CREATOR = 'facade.auth.token_auth.token_creator'
# REST_AUTH_TOKEN_MODEL = 'facade.inouts.ExpiringToken'
import os

from exchange.settings import env

REST_AUTH_REGISTER_SERIALIZERS = {
    'REGISTER_SERIALIZER': 'core.serializers.auth.RegisterSerializer'
}

EXPIRING_TOKEN_LIFETIME = 60 * 60
ACCOUNT_ADAPTER = 'core.auth.adapters.AccountAdapter'

OLD_PASSWORD_FIELD_ENABLED = True

SESSION_COOKIE_AGE = 2 * 24 * 60 * 60  # two days

PASSWORD_MIN_LENGTH = 1

AUTHENTICATION_BACKENDS = (
    'core.auth.backends.CIUsernameAuthBackend',
    'django.contrib.auth.backends.ModelBackend',
)

ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_CONFIRM_EMAIL_ON_GET = True

CAPTCHA_ENABLED = True
CAPTCHA_TIMEOUT = 60 * 60
RECAPTCHA_SECRET = env('RECAPTCHA_SECRET')
IP_MASK = env('CAPTCHA_ALLOWED_IP_MASK', default=r'172.\d{1,3}.\d{1,3}.\d{1,3}')
CAPTCHA_ALLOWED_IP_MASK = fr"{IP_MASK}"

DISALLOW_COUNTRY = ('', 'US', 'BS', 'BW', 'KH', 'KP', 'ET', 'GH', 'IR', 'RS', 'LK', 'SY', 'TT', 'TN', 'YE')
