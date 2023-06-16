from django.apps import AppConfig


class ExchangeAdminConfig(AppConfig):
    name = 'admin_panel'

    def ready(self):
        import admin_panel.signals  # noqa
