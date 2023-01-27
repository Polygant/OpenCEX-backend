import django_filters
from django_filters.rest_framework import filterset
from django_filters.rest_framework.backends import DjangoFilterBackend

from core.currency import CurrencyModelField
from core.pairs import PairModelField


class FilterSet(filterset.FilterSet):
    class Meta:
        filter_overrides = {
            PairModelField: {
                'filter_class': django_filters.CharFilter,
            },
            CurrencyModelField: {
                'filter_class': django_filters.CharFilter,
            },
        }


class FilterBackend(DjangoFilterBackend):
    filterset_base = FilterSet
