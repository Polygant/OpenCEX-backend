from drf_spectacular.extensions import OpenApiAuthenticationExtension

from core.models import DisabledCoin, PairSettings


def is_pair_disabled(pair, disabled_type=None):
    return DisabledCoin.is_coin_disabled(pair.base.code, disabled_type) \
            or DisabledCoin.is_coin_disabled(pair.quote.code, disabled_type) \
            or not PairSettings.is_pair_enabled(pair.code)


class HMACAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'core.auth.api_hmac_auth.HMACAuthentication'  # full import path OR class ref
    name = 'HMACAuthentication'  # name used in the schema

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'basic',
        }
