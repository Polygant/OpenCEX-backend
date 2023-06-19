import re
from copy import deepcopy

from django.db import models
from django_filters.constants import EMPTY_VALUES
from django_filters.filters import CharFilter, DateFilter
from django_filters.rest_framework import DjangoFilterBackend
from django_filters.rest_framework.filterset import FilterSet, FILTER_FOR_DBFIELD_DEFAULTS

from core.currency import Currency, CurrencyModelField
from core.models.inouts.pair import Pair, PairModelField


class CurrencyModelFilter(CharFilter):
    field_value_class = Currency

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


class PairModelFilter(CurrencyModelFilter):
    field_value_class = Pair


FILTER_FOR_DBFIELD_DEFAULTS = deepcopy(FILTER_FOR_DBFIELD_DEFAULTS)
FILTER_FOR_DBFIELD_DEFAULTS.update({
    CurrencyModelField: {'filter_class': CurrencyModelFilter},
    PairModelField: {'filter_class': PairModelFilter},
    models.DateTimeField: {'filter_class': DateFilter},
    models.DateField: {'filter_class': DateFilter},
})


def reparse_query_data(query_data):
    res = {}
    for param, value in query_data.items():
        if '[' and ']' in param:
            new_param_name = param.split('[')[0]
            regex = re.compile('%s\[([\w\d_]+)\]' % new_param_name)
            match = regex.match(param)
            inner_key = match.group(1)
            if inner_key == 'start':
                res[new_param_name+'__gte'] = value
            elif inner_key == 'end':
                res[new_param_name + '__lte'] = value
        else:
            res[param] = value
    return res


class GenericFilterset(FilterSet):
    FILTER_DEFAULTS = FILTER_FOR_DBFIELD_DEFAULTS

    def __init__(self, *args, **kwargs):
        super(GenericFilterset, self).__init__(*args, **kwargs)
        self.data = reparse_query_data(self.data)
    
    def filter_queryset(self, queryset):
        # dirty hack
        data = dict(self.data)
        for name, value in self.form.cleaned_data.items():
            if name in data and name == 'id':
                value = data[name]
                if isinstance(value, list) and len(value) > 1:
                    lookup = f'{name}__in'
                    queryset = queryset.filter(**{lookup: value})
                else:
                    if isinstance(value, list):
                        value = value[0]
                    queryset = self.filters[name].filter(queryset, value)

            else:
                queryset = self.filters[name].filter(queryset, value)
        return queryset


class GenericAllFieldsFilter(DjangoFilterBackend):
    filterset_base = GenericFilterset

    def get_filterset_class(self, view, queryset=None):
        """
        Return the `FilterSet` class used to filter the queryset.
        """
        defined_filterset_fields = getattr(view, 'filterset_fields', None)
        filterset_fields = {}
        model_fields = {f.name: f for f in queryset.model._meta.fields}
        for field_name in defined_filterset_fields:
            if field_name in model_fields and type(model_fields[field_name]) in [models.DateField, models.DateTimeField]:
                lookups = ['gte', 'lte',]
            else:
                lookups = ['exact']
            filterset_fields[field_name] = lookups

        if defined_filterset_fields and queryset is not None:
            MetaBase = getattr(self.filterset_base, 'Meta', object)

            class AutoFilterSet(self.filterset_base):
                class Meta(MetaBase):
                    model = queryset.model
                    fields = filterset_fields

            return AutoFilterSet

        return None