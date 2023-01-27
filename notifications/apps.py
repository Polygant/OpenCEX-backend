import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)


class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        # noinspection PyUnresolvedReferences
        import notifications.signal_handlers
