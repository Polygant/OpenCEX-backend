from celery import shared_task
from django.utils.module_loading import autodiscover_modules

from core.consts.settings import DEFAULT_SETTINGS


@shared_task
def initialize_settings():
    autodiscover_modules('default_settings')
    from core.models.settings import Settings
    for name, value in DEFAULT_SETTINGS.items():
        Settings.objects.get_or_create(name=name, defaults={'value': value})