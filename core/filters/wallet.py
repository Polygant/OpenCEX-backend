from django_filters import rest_framework as filters

from core.currency import CurrencyModelField
from core.models.wallet_history import WalletHistoryItem


class WalletHistoryFilter(filters.FilterSet):

    class Meta:
        model = WalletHistoryItem
        fields = (
            'state',
            'operation_type',
            'currency',
            'confirmed',
            'paygate_id',
            'paygate_method',
        )
        filter_overrides = {
            # because of field gets string currency code
            CurrencyModelField: {
                'filter_class': filters.CharFilter,
            }
        }