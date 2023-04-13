import os

from exchange.settings import env

DISABLE_REGISTRATION = False

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FILE_CHARSET = 'utf-8'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'l35966o%0mtqpv+y@)^f=he6$p82ut=j6ea=hpndz!&$)1m@ck'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG', default=False)
IS_TEST = env('IS_TEST', default=False)

ALLOWED_HOSTS = ['0.0.0.0/0', env('INSTANCE_NAME'), env('DOMAIN'), ]
if IS_TEST:
    ALLOWED_HOSTS.append('localhost')
    ALLOWED_HOSTS.append('127.0.0.1')

INSTALLED_APPS = [
    'channels',
    'maintenance_mode',
    'behave_django',
    'cryptocoins',
    'core',
    'notifications',
    'bots',
    'public_api',
    'sci',
    'seo',
    'admin_panel',

    'modeltranslation',
    'admin_tools',
    'admin_tools.theming',
    'admin_tools.menu',
    'admin_tools.dashboard',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',

    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'django_filters',
    'django_countries',
    'django_user_agents',
    'dj_rest_auth',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',  # needed, cause bug https://github.com/Tivix/django-rest-auth/issues/412
    'dj_rest_auth.registration',
    'corsheaders',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'rangefilter',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'core.middleware.force_default_language_middleware',
    'core.middleware.SetupTranslationsLang',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.AccessLogsMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'maintenance_mode.middleware.MaintenanceModeMiddleware',
    'django_otp.middleware.OTPMiddleware',
]


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        # 'APP_DIRS': True,
        'OPTIONS': {
            'loaders': [
                'admin_tools.template_loaders.Loader',
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'maintenance_mode.context_processors.maintenance_mode',
            ],
        },
    },
]

WSGI_APPLICATION = 'exchange.wsgi.application'
ASGI_APPLICATION = 'exchange.routing.application'

ROOT_URLCONF = 'exchange.urls'

SITE_ID = 1

INSTANCE_NAME = env('INSTANCE_NAME', default='test')
PROJECT_NAME = env('PROJECT_NAME', default='test')

# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

_AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

DATETIME_FORMAT = '%s'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

# STATIC_URL = '/static/'
# STATIC_ROOT = 'static/static'
STATICFILES_DIRS = ()
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/staticfiles/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/upload/'


MAINTENANCE_MODE = None
MAINTENANCE_MODE_STATE_BACKEND = 'maintenance_mode.backends.LocalFileBackend'
MAINTENANCE_MODE_STATE_FILE_PATH = 'maintenance_mode_state.txt'
MAINTENANCE_MODE_IGNORE_ADMIN_SITE = False
MAINTENANCE_MODE_IGNORE_ANONYMOUS_USER = False
MAINTENANCE_MODE_IGNORE_AUTHENTICATED_USER = False
MAINTENANCE_MODE_IGNORE_STAFF = False
MAINTENANCE_MODE_IGNORE_SUPERUSER = False
MAINTENANCE_MODE_GET_CLIENT_IP_ADDRESS = None
MAINTENANCE_MODE_STATUS_CODE = 503
MAINTENANCE_MODE_RETRY_AFTER = 600  # 10 min
MAINTENANCE_MODE_TEMPLATE = '503.html'

COMMON_HTTP_PROXY = {
    'http': '127.0.0.1:8888',
    'https': '127.0.0.1:8888',
}

TELEGRAM_CHAT_ID = env('TELEGRAM_CHAT_ID')
TELEGRAM_ALERTS_CHAT_ID = env('TELEGRAM_ALERTS_CHAT_ID')
TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN')

VUE_UPLOAD_PATH = "uploads/"

VALID_IMAGE_EXTENSION = [".png", ".jpg", ".jpeg"]
VALID_CHAT_ATTACHMENT_EXTENSION = ['.jpg', '.jpeg', '.bmp', '.png', '.pdf', '.doc', '.docx']

DOMAIN = env('DOMAIN', default='example.com')

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'