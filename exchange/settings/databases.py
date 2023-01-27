# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases
from exchange.settings import env

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASS'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default=5432),
        'CONN_MAX_AGE': env('DB_CONN_MAX_AGE', default=10)
    }
}
