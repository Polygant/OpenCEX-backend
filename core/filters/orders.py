from django_filters import rest_framework as filters

from core.consts.orders import (
    ORDER_OPENED,
    ORDER_CLOSED,
    ORDER_CANCELED,
)
from core.models.orders import Order
from core.pairs import PairModelField


class OrdersFilter(filters.FilterSet):
    """
    We need be able to get custom combinations of order state
    """
    STATES_OPENED = (ORDER_OPENED, )
    STATES_CLOSED_OR_CANCELLED = (ORDER_CLOSED, ORDER_CANCELED)

    opened = filters.BooleanFilter(method='filter_opened')

    def filter_opened(self, queryset, name, value):
        if value:
            states = self.STATES_OPENED
        else:
            states = self.STATES_CLOSED_OR_CANCELLED

        return queryset.filter(
            state__in=states,
        )

    class Meta:
        model = Order
        fields = (
            'opened',
            'operation',
            'executed',
            'pair',
            'type',
            'state',
        )
        filter_overrides = {
            PairModelField: {
                'filter_class': filters.CharFilter,
            }
        }
