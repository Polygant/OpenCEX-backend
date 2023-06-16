import django_filters
from django_filters.rest_framework import filterset
from django_filters.rest_framework.backends import DjangoFilterBackend

from admin_rest.filters import PairModelFilter
from core.currency import CurrencyModelField
from core.models.inouts.pair import PairModelField


class FilterSet(filterset.FilterSet):
    class Meta:
        filter_overrides = {
            PairModelField: {
                'filter_class': PairModelFilter,
            },
            CurrencyModelField: {
                'filter_class': django_filters.CharFilter,
            },
        }


class FilterBackend(DjangoFilterBackend):
    filterset_base = FilterSet
