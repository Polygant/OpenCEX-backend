from django.apps import AppConfig

from cryptocoins.tokens_manager import register_tokens_and_pairs


class CryptocoinsConfig(AppConfig):
    name = 'cryptocoins'

    def ready(self):
        register_tokens_and_pairs()
