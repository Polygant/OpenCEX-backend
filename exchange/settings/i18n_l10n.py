import os
from .common import BASE_DIR


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

LANGUAGES = (
    ('en', 'English'),
    ('ru', 'Russian'),
)
LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)
LANGUAGE_COOKIE_NAME = 'lang'

MODELTRANSLATION_LANGUAGES = (
    'ru',
    'en',
    # 'es',  #TODO add if needed
    # 'fr',
)
MODELTRANSLATION_DEFAULT_LANGUAGE = 'en'
