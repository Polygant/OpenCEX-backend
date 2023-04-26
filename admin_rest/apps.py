from django.apps import AppConfig

from django.apps import apps
import importlib
from django.utils.module_loading import module_has_submodule


class AdminRestConfig(AppConfig):
    name = 'admin_rest'

    def ready(self):
        app_configs = apps.get_app_configs()

        for app_config in app_configs:
            module_path = app_config.module.__name__
            if module_has_submodule(importlib.import_module(module_path), 'admin_rest'):
                admin_rest_module = importlib.import_module(module_path + '.admin_rest')

