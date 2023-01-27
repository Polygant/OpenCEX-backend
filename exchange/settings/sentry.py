import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from exchange.settings import env


# Sentry
SENTRY_DSN = env('SENTRY_DSN')

if SENTRY_DSN and SENTRY_DSN != '':
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ]
    )
