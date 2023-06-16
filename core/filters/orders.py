from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES

from admin_rest.filters import PairModelFilter
from core.consts.currencies import CURRENCIES_LIST
from core.consts.orders import (
    ORDER_OPENED,
    ORDER_CLOSED,
    ORDER_CANCELED,
)
from core.currency import Currency, CurrencyModelField
from core.models import Exchange
from core.models.inouts.pair import PairModelField
from core.models.orders import Order


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
                'filter_class': PairModelFilter,
            }
        }


class CurrencyModelFilter(filters.CharFilter):
    field_value_class = Currency
    field_class = CurrencyModelField(choices=CURRENCIES_LIST).formfield

    def filter(self, qs, value):
        if value is None:
            return self.get_method(qs)(**{self.field_name: None})

        if value in EMPTY_VALUES:
            return qs

        if self.field_value_class.exists(value):
            value = self.field_value_class.get(value).id
        else:
            return qs.none()

        if self.distinct:
            qs = qs.distinct()
        qs = self.get_method(qs)(**{self.field_name: value})
        return qs


class ExchangeFilter(filters.FilterSet):
    state = filters.ChoiceFilter(field_name='order__state', choices=Order.STATES)
    operation = filters.ChoiceFilter(field_name='operation', choices=Exchange.OPERATION_LIST)
    base_currency = CurrencyModelFilter(field_name='base_currency')
    quote_currency = CurrencyModelFilter(field_name='quote_currency')

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).select_related('order', )

    class Meta:
        model = Exchange
        fields = [
            'state',
            'operation',
            'base_currency',
            'quote_currency',
        ]
