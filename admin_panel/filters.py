import pytz
from django.conf import settings
from django.contrib.admin import DateFieldListFilter
from django.contrib.admin.filters import FieldListFilter
from django.contrib.admin.filters import SimpleListFilter
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.aggregates import Count
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.consts.currencies import CURRENCIES_LIST
from core.models import WalletTransactions, Order
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import REASON_WITHDRAWAL
from core.models.inouts.sci import GATES

User = get_user_model()


class MyDateFilter(DateFieldListFilter):
    def __init__(self, field, request, params, model, model_admin, field_path):
        params_copy = {}
        params_copy.update(params)
        x = DateFieldListFilter(field, request, params_copy, model, model_admin, field_path)
        if not x.date_params:
            params = x.links[1][1]
        DateFieldListFilter.__init__(self, field, request, params, model, model_admin, field_path)

        now = timezone.now()
        # When time zone support is enabled, convert "now" to the user's time
        # zone so Django's definition of "Today" matches what the user expects.
        if timezone.is_aware(now):
            now = timezone.localtime(now)

        if isinstance(field, models.DateTimeField):
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:       # field is a inouts.DateField
            today = now.date()

        this_year = today.replace(month=1, day=1)
        prev_year = today.replace(year=today.year - 1, month=1, day=1)

        self.links = list(self.links) + [
            ('Last year', {
                self.lookup_kwarg_since: str(prev_year),
                self.lookup_kwarg_until: str(this_year),
            }
            )
        ]


class WithdrawalReasonFilter(SimpleListFilter):
    title = 'reason'  # or use _('country') for translated title
    parameter_name = 'reason'
    REASONS = [(REASON_WITHDRAWAL, 'Withdrawal')]

    def lookups(self, request, model_admin):
        return self.REASONS

    def queryset(self, request, queryset):
        return queryset.filter(reason=self.value()) if self.value() else queryset


class TopupReasonFilter(WithdrawalReasonFilter):
    REASONS = [(REASON_TOPUP, 'TOPUP')]


class CurrencyFilter(SimpleListFilter):
    title = 'currency'
    parameter_name = 'currency'

    def lookups(self, request, model_admin):
        return CURRENCIES_LIST

    def queryset(self, request, queryset):
        return queryset.filter(**{self.parameter_name: self.value()}) if self.value() else queryset


class WalletTransactionStateFilter(SimpleListFilter):
    title = 'state'
    parameter_name = 'state'

    def lookups(self, request, model_admin):
        return WalletTransactions.STATES

    def queryset(self, request, queryset):
        return queryset.filter(**{self.parameter_name: self.value()}) if self.value() else queryset


class WalletTransactionStatusFilter(SimpleListFilter):
    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return WalletTransactions.STATUS_LIST

    def queryset(self, request, queryset):
        return queryset.filter(**{self.parameter_name: self.value()}) if self.value() else queryset


class CurrencyFieldFilter(FieldListFilter):

    def expected_parameters(self):
        return [self.field_path]

    def value(self):
        return self.used_parameters.get(self.field_path)

    def choices(self, changelist):
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.field_path]),
            'display': 'All',
        }
        for lookup, title in CURRENCIES_LIST:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.field_path: lookup}),
                'display': title,
            }


class AddressTypeFilter(SimpleListFilter):
    title = 'Addresses'
    parameter_name = 'address_type'

    def lookups(self, request, model_admin):
        return [
            ('all', 'All'),
            ('old', 'Old'),
            ('new', 'New')
        ]

    def queryset(self, request, queryset):
        last_regen = pytz.UTC.localize(settings.LATEST_ADDRESSES_REGENERATION)
        if self.value() == 'new':
            return queryset.filter(wallet__created__gt=last_regen)
        elif self.value() == 'old':
            return queryset.filter(wallet__created__lte=last_regen)
        return queryset


class FeeRateFilter(SimpleListFilter):
    title = 'fee_rate'
    parameter_name = 'fee_rate'

    def lookups(self, request, model_admin):
        return [(i, i) for i in model_admin.model.objects.all().values('fee_rate').annotate(c=Count('fee_rate')).values_list('fee_rate', flat=True)]

    def queryset(self, request, queryset):
        return queryset.filter(fee_rate=float(self.value())) if self.value() else queryset


class GateFilter(SimpleListFilter):
    title = 'gate'
    parameter_name = 'sci_gate_id'

    def lookups(self, request, model_admin):
        return [(0, 'crypto')] + [(k, v.NAME) for k, v in GATES.items()]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        if self.value() == '0':
            queryset = queryset.filter(gate_id__isnull=True)
        else:
            queryset = queryset.filter(gate_id=self.value())
        return queryset


class OrderTypeFilter(SimpleListFilter):
    title = 'order type'
    parameter_name = 'order_type'

    def lookups(self, request, model_admin):
        return Order.ORDER_TYPES

    def queryset(self, request, queryset):
        return queryset.filter(type=self.value()) if self.value() else queryset
