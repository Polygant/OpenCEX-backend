import logging

from django.contrib import admin
from django.db.models import Q, Sum, F
from rangefilter.filters import DateRangeFilter

from core.enums.profile import UserTypeEnum
from core.models import Balance, WithdrawalRequest, Settings
from core.models.inouts.withdrawal import WithdrawalLimitLevel, WithdrawalUserLimit
from core.models.stats import InoutsStats
from core.models.facade import SmsConfirmationHistory
from lib.admin import BaseModelAdmin, ReadOnlyMixin, ImmutableMixIn

log = logging.getLogger(__name__)


@admin.register(InoutsStats)
class InoutsStatsAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['currency', 'deposits', 'withdrawals', 'total', 'in_orders', 'free', 'withdrawals_pending']
    global_actions = ['refresh']
    ordering = ('currency',)

    def get_queryset(self, request):
        exclude_qs = (
                Q(user__profile__user_type=UserTypeEnum.staff.value)
                | Q(user__profile__user_type=UserTypeEnum.bot.value)
                | Q(user__email__endswith='@bot.com')
                | Q(user__is_staff=True)
        )

        balance_summary = Balance.objects.exclude(exclude_qs).values(
            'currency'
        ).annotate(
            free=Sum('amount'),
            in_orders=Sum('amount_in_orders'),
            total=Sum(F('amount') + F('amount_in_orders')),
        )
        withdrawals_pending = WithdrawalRequest.objects.filter(
            state=WithdrawalRequest.STATE_PENDING,
        ).exclude(exclude_qs).values('currency').annotate(
            withdrawals_pending=Sum('amount'),
        )

        self._balance_summary_dict = {b['currency']: b for b in balance_summary}
        self._withdrawals_pending_dict = {wp['currency']: wp for wp in withdrawals_pending}
        return super(InoutsStatsAdmin, self).get_queryset(request)

    def total(self, obj):
        return self._balance_summary_dict.get(obj.currency, {}).get('total') or 0

    def free(self, obj):
        return self._balance_summary_dict.get(obj.currency, {}).get('free') or 0

    def in_orders(self, obj):
        return self._balance_summary_dict.get(obj.currency, {}).get('in_orders') or 0

    def withdrawals_pending(self, obj):
        return self._withdrawals_pending_dict.get(obj.currency, {}).get('withdrawals_pending') or 0

    # custom actions
    @admin.action(permissions=True)
    def refresh(self, request, queryset):
        InoutsStats.refresh()

    refresh.short_description = 'Update stats'


@admin.register(Settings)
class SettingsAdmin(BaseModelAdmin):
    no_delete = False
    fields = ('value',)
    list_filter = ['name', 'value', ('updated', DateRangeFilter), ]


@admin.register(SmsConfirmationHistory)
class SmsConfirmationHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    search_fields = ['user__email', 'phone']
    list_filter = ['action_type', 'verification_type', 'is_success', ('created', DateRangeFilter), ]


@admin.register(WithdrawalLimitLevel)
class WithdrawalLimitLevelAdmin(BaseModelAdmin):
    list_display = [
        'id',
        'level',
        'amount',
    ]
    no_delete = False


@admin.register(WithdrawalUserLimit)
class WithdrawalUserLimitAdmin(BaseModelAdmin):
    no_delete = False
    search_fields = ['user__email']
    list_display = [
        'id',
        'user',
        'limit_amount',
    ]

    def limit_amount(self, obj: WithdrawalUserLimit):
        return f'{obj.limit_id} | {obj.limit.amount}'
