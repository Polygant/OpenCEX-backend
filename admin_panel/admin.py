import csv
import json
import logging
import time
from typing import List

from allauth.account.admin import EmailAddressAdmin
from allauth.account.models import EmailAddress
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db import transaction
from django.db.models import F, Value, Case, When, ExpressionWrapper, Count
from django.db.models import Q
from django.db.models import Sum
from django.db.transaction import atomic
from django.forms import BaseInlineFormSet
from django.forms.models import ModelForm
from django.http import HttpResponse
from django.urls.base import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _, ugettext_lazy
from django_otp.plugins.otp_totp.models import TOTPDevice
from rangefilter.filters import DateRangeFilter
from rest_framework.exceptions import ValidationError

from admin_panel.filters import CurrencyFilter, CurrencyFieldFilter, WalletTransactionStateFilter, \
    WalletTransactionStatusFilter, OrderTypeFilter
from admin_panel.filters import FeeRateFilter
from admin_panel.filters import GateFilter
from admin_panel.filters import PairsFilter
from admin_panel.filters import TopupReasonFilter
from admin_panel.models import AllOrder, EmailAddressVerified
from admin_panel.models import AllOrderNoBot
from admin_panel.models import Balance
from admin_panel.models import ExchangeUser
from admin_panel.models import Match
from admin_panel.models import Topups
from admin_panel.models import Transaction
from admin_panel.models import UserDailyStat
from admin_panel.models import WithdrawalRequest
from core.consts.inouts import DISABLE_COIN_STATES
from core.currency import Currency
from core.models import AccessLog, Message, WithdrawalFee, FeesAndLimits, WalletTransactions, WalletTransactionsRevert, \
    Exchange, ExecutionResult, OrderStateChangeHistory, ExternalPricesHistory, TradesAggregatedStats, UserPairDailyStat, \
    WalletHistoryItem, UserRestrictions, PayGateTopup, DisabledCoin, PairSettings
from core.models.inouts.dif_balance import DifBalance
from cryptocoins.models.stats import DepositsWithdrawalsStats
from cryptocoins.tasks import calculate_topups_and_withdrawals
from cryptocoins.utils.stats import generate_stats_fields
from lib.helpers import BOT_RE
from admin_panel.utils import MyPaginator
from core.balance_manager import BalanceManager
from core.consts.orders import ORDER_CLOSED, BUY
from core.consts.orders import SELL
from core.exceptions.inouts import NotEnoughFunds
from core.models.cryptocoins import UserWallet
from core.models.facade import LoginHistory, CoinInfo
from core.models.facade import Profile, SourceOfFunds
from core.models.facade import SmsHistory
from core.models.facade import TwoFactorSecretHistory
from core.models.facade import TwoFactorSecretTokens
from core.models.facade import UserExchangeFee
from core.models.facade import UserFee
from core.models.facade import UserKYC
from core.models.inouts.sci import GATES
from core.models.inouts.transaction import POSITIVE_REASONS, REASON_MANUAL_TOPUP
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import REASON_WITHDRAWAL
from core.models.inouts.transaction import TRANSACTION_CANCELED
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.orders import Order
from core.models.orders import OrderChangeHistory
from lib.admin import BaseModelAdmin, ImmutableMixIn, NoAddMixIn
from lib.admin import ImmutableMixIn
from lib.admin import ReadOnlyMixin
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


@classmethod
def model_field_exists(cls, field):
    try:
        # Django 3.1 and above
        from django.db.models import FieldDoesNotExist
    except ImportError:
        from django.core.exceptions import FieldDoesNotExist

    try:
        cls._meta.get_field(field)
        return True
    except FieldDoesNotExist:
        return False


models.Model.field_exists = model_field_exists


class ProfileAdminInline(admin.StackedInline):
    model = Profile

    def get_readonly_fields(self, request, obj=None):
        fields = super(ProfileAdminInline, self).get_readonly_fields(request, obj=obj)
        is_superuser = request.user.is_superuser
        if not is_superuser:
            fields = list(fields)
            fields.extend(['is_auto_orders_enabled', 'p2p_codes_enabled', 'payouts_freezed_till'])
        fields = tuple(set(fields))
        return fields


class TopupAdminList(admin.SimpleListFilter):
    model = Topups


class NonUpdateForm(ModelForm):
    def is_valid(self):
        return True

    def save(self, commit=True):
        return self.instance


class KycInline(admin.TabularInline):
    model = UserKYC
    template = 'kyc.html'
    form = NonUpdateForm

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TwoFactorSecretTokensInline(admin.TabularInline):
    model = TwoFactorSecretTokens
    fields = ['status', 'last_updated']
    readonly_fields = ['status', 'last_updated']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def status(self, obj):
        return 'ON' if TwoFactorSecretTokens.is_enabled_for_user(obj.user) else 'OFF'

    def last_updated(self, obj):
        return obj.updated


class TwoFactorSecretHistoryInline(admin.TabularInline):
    model = TwoFactorSecretHistory
    fields = ['created', 'status']
    readonly_fields = ['created', 'status']
    ordering = ('-created',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SmsHistoryInline(admin.TabularInline):
    model = SmsHistory
    fields = ['created', 'phone', 'withdrawals_sms_confirmation']
    readonly_fields = ['created', 'phone', 'withdrawals_sms_confirmation']
    ordering = ('-created',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LoginHistoryInline(admin.TabularInline):
    model = LoginHistory
    fields = ['created', 'ip', 'user_agent']
    readonly_fields = ['created', 'ip', 'user_agent']
    ordering = ('-created',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UserWalletInline(admin.TabularInline):
    model = UserWallet
    fields = ('currency', 'address')
    readonly_fields = ('currency', 'address')

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


class KycApproveInline(admin.TabularInline):
    model = UserKYC
    fields = ['forced_approve', ]


class EmailConfirmationInline(admin.TabularInline):
    model = EmailAddress
    fields = ['verified', ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BalancesInline(ReadOnlyMixin, admin.TabularInline):
    model = Balance
    fields = ['currency', 'amount', 'amount_in_orders', 'total']
    can_delete = False

    def total(self, obj):
        return obj.amount + obj.amount_in_orders

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.order_by('currency')

    def get_readonly_fields(self, request, obj=None):
        return ReadOnlyMixin.get_readonly_fields(self, request, obj=obj) + ['total']


class HistoryInline(admin.TabularInline):
    model = OrderChangeHistory
    fields = ('created', 'quantity', 'price', 'otc_percent', 'otc_limit', 'stop', )
    readonly_fields = (
        'created',
        'order',
        'quantity',
        'price',
        'otc_percent',
        'otc_limit',
        'stop',
    )
    ordering = ('-created',)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


# Cannot filter a query once a slice has been taken.
class OrderFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kwargs = {self.fk.name: kwargs['instance']}
        qs = AllOrder.objects.filter(**_kwargs).filter(executed=True).order_by('-created')
        qs = qs[:50]
        self.queryset = qs


class OrderInline(ReadOnlyMixin, admin.TabularInline):
    model = AllOrder
    fields = [
        'created',
        'pair',
        'order_operation',
        'type',
        'quantity',
        'quantity_left',
        'price',
        'sum',
        'state_colored',
    ]
    can_delete = False
    show_change_link = True
    formset = OrderFormSet

    def created(self, obj):
        return obj.in_transaction.created

    def order_operation(self, obj):
        if obj.operation == SELL:
            return mark_safe('<span style="color:red">SELL</span>')
        if obj.operation == BUY:
            return mark_safe('<span style="color:green">BUY</span>')

        return '-'

    def state_colored(self, obj):
        color = 'red'
        if obj.state == Order.STATE_OPENED:
            color = 'green'
        elif obj.state == Order.STATE_CANCELLED:
            color = 'darkorange'

        return mark_safe(f'<span style="color:{color}">{obj.get_state_display()}</span>')

    def sum(self, obj):
        if obj.quantity and obj.price:
            q_left = to_decimal(obj.quantity_left or 0)
            quantity = to_decimal(obj.quantity)
            price = to_decimal(obj.price)
            return round((quantity - q_left) * price, 6)

        return '-'

    def get_readonly_fields(self, request, obj=None):
        return ReadOnlyMixin.get_readonly_fields(self, request, obj=obj) + [
            'state_colored',
            'order_operation',
            'sum',
        ]

    state_colored.short_description = 'State'
    order_operation.short_description = 'Operation'


# Cannot filter a query once a slice has been taken.
class TransactionFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kwargs = {self.fk.name: kwargs['instance']}
        qs = Transaction.objects.filter(**_kwargs).order_by('-created')
        qs = qs.filter(reason__in=[
            REASON_TOPUP,
            REASON_WITHDRAWAL,
        ])
        qs = qs[:50]

        self.queryset = qs


class TransactionsInline(ReadOnlyMixin, admin.TabularInline):
    model = Transaction
    fields = ['created', 'reason_colored', 'currency', 'amount', 'state_colored']
    can_delete = False
    formset = TransactionFormSet
    show_change_link = True

    def created(self, obj):
        return obj.in_transaction.created

    def reason_colored(self, obj):
        if obj.reason not in POSITIVE_REASONS:
            return mark_safe(f'<span style="color:red">{obj.get_reason_display()}</span>')
        else:
            return mark_safe(f'<span style="color:green">{obj.get_reason_display()}</span>')

    def state_colored(self, obj):
        color = 'darkorange'
        if obj.state == TRANSACTION_COMPLETED:
            color = 'green'
        elif obj.state == TRANSACTION_CANCELED:
            color = 'red'

        return mark_safe(f'<span style="color:{color}">{obj.get_state_display()}</span>')

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return ReadOnlyMixin.get_readonly_fields(self, request, obj=obj) + ['state_colored', 'reason_colored']

    state_colored.short_description = 'State'
    reason_colored.short_description = 'Reason'


class FeeInline(admin.StackedInline):
    model = UserFee

class ExchangeFeeInline(admin.StackedInline):
    model = UserExchangeFee


class SOFInline(admin.TabularInline):
    model = SourceOfFunds

    readonly_fields = (
        'is_beneficiary',
        'profession_value',
        'source_value',
    )
    exclude = (
        'profession',
        'source',
    )

    def profession_value(self, obj):
        if obj.profession is None:
            return 'Not set'

        result = []
        # iterate over professions array
        for i in obj.profession:
            # iterate over profession choices
            for j in obj.PROFESSIONS:
                _id, text = j
                if _id == i:
                    result.append(str(text))

        return ', '.join(result)

    def source_value(self, obj):
        if obj.source is None:
            return 'Not set'

        result = []
        for i in obj.source:
            for j in obj.SOURCES:
                _id, text = j
                if _id == i:
                    result.append(str(text))

        return ', '.join(result)


@admin.register(UserDailyStat)
class UserPairDailyStatAdmin(BaseModelAdmin):
    class C1(CurrencyFilter):
        title = 'currency1'
        parameter_name = 'currency1'

    class C2(CurrencyFilter):
        title = 'currency2'
        parameter_name = 'currency2'

    list_filter = ['day', PairsFilter, C2, C1]
    search_fields = ['user__email']
    list_display = ['user', 'pair', 'day', 'currency1', 'currency2', 'volume_got1', 'volume_got2', 'fee_amount_paid1', 'fee_amount_paid2', 'volume_spent1', 'volume_spent2']
    readonly_fields = list_display

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(fee_amount_paid1=0, fee_amount_paid2=0)


@admin.register(DifBalance)
class DifBalanceAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    display_fields = ['created', 'user', 'type', 'currency', 'diff', 'diff_percent',
                      'balance', 'old_balance', 'txs_amount', 'calc_balance', 'sum_diff']
    list_display = display_fields
    fields = display_fields
    readonly_fields = display_fields

    filterset_fields = ['created', 'currency']
    search_fields = [
        'user__email',
        'user__id',
    ]
    ordering = ('-id',)


@admin.register(EmailAddressVerified)
class EmailConfirmationAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin, EmailAddressAdmin):
    pass


@admin.register(AccessLog)
class AccessLogAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = [
        'created',
        'ip',
        'username',
        'method',
        'uri',
        'status',
        'referer',
        'user_agent']
    fields = [
        'created',
        'ip',
        'username',
        'method',
        'uri',
        'status',
        'referer',
        'user_agent']
    search_fields = [
        'username',
        'uri',
        'user_agent',
        'ip'
    ]
    filterset_fields = ['created', 'method', 'status']
    ordering = ('-created',)


@admin.register(LoginHistory)
class LoginHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['created', 'ip', 'user_agent']
    readonly_fields = ['created', 'ip', 'user_agent']
    ordering = ('-created',)


@admin.register(Message)
class MessageAdmin(BaseModelAdmin):
    no_delete = False


@admin.register(Profile)
class ProfileAdmin(NoAddMixIn, BaseModelAdmin):
    list_display = (
        'id', 'created', 'user_type', 'email', 'user_id', 'payouts_freezed_till', 'language', 'register_ip',
    )
    readonly_fields = (
        'id',
        'created',
        'updated',
        'register_ip',
    )
    search_fields = (
        'id',
        'user__email',
        'user__id',
    )
    list_filter = (
        'user__email',
        'user__id',
        # 'type',
        'country',
    )

    def country(self, obj: Profile):
        return obj.country

    def email(self, obj):
        return obj.user.email

    def user_id(self, obj):
        return obj.user.id


@admin.register(SmsHistory)
class SmsHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['user', 'created', 'phone', 'withdrawals_sms_confirmation']
    filterset_fields = ['created']
    search_fields = ['user__email', 'phone']
    ordering = ('-created',)


@admin.register(SourceOfFunds)
class SourceOfFundsAdmin(BaseModelAdmin):
    fields = ['user', 'is_beneficiary', 'profession_value', 'source_value']
    list_display = [
        'user',
        'is_beneficiary',
        'profession_value',
        'source_value']
    readonly_fields = (
        'is_beneficiary',
        'profession_value',
        'source_value',
    )

    def profession_value(self, obj):
        if obj.profession is None:
            return 'Not set'

        result = []
        # iterate over professions array
        for i in obj.profession:
            # iterate over profession choices
            for j in obj.PROFESSIONS:
                _id, text = j
                if _id == i:
                    result.append(str(text))

        return ', '.join(result)

    def source_value(self, obj):
        if obj.source is None:
            return 'Not set'

        result = []
        for i in obj.source:
            for j in obj.SOURCES:
                _id, text = j
                if _id == i:
                    result.append(str(text))

        return ', '.join(result)


@admin.register(TwoFactorSecretHistory)
class TwoFactorSecretHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    fields = ['created', 'status']
    readonly_fields = ['created', 'status']
    ordering = ('-created',)


@admin.register(TwoFactorSecretTokens)
class TwoFactorSecretTokensAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['id', 'email', 'status', 'last_updated']
    search_fields = (
        'id',
        'user__email',
        'user__id',
    )
    actions = (
        'disable',
    )

    def status(self, obj):
        return 'ON' if TwoFactorSecretTokens.is_enabled_for_user(obj.user) else 'OFF'

    def last_updated(self, obj):
        return obj.updated

    def email(self, obj):
        return obj.user.email

    @admin.action(permissions=('change', ))
    def disable(self, request, queryset):
        """
        :param request:
        :param queryset:
        :type queryset: list[TwoFactorSecretTokens]
        """
        try:
            with atomic():
                for tfs in queryset:
                    tfs.drop()
        except BaseException as e:
            messages.error(request, e)



@admin.register(UserExchangeFee)
class UserExchangeFeeAdmin(BaseModelAdmin):
    no_delete = False


@admin.register(UserFee)
class UserFeeAdmin(BaseModelAdmin):
    no_delete = False


@admin.register(UserKYC)
class UserKYCAdmin(NoAddMixIn, BaseModelAdmin):
    search_fields = [
        'user__username',
    ]
    list_filter = [
        'reviewAnswer',
        'forced_approve',
    ]
    fields = [
        'user',
        'applicantId',
        'review_answer_colored',
        'last_kyc_data_update',
        'forced_approve',
        'moderationComment',
        'rejectLabels',
        'pretty_data',
    ]
    readonly_fields = [
        'user',
        'applicantId',
        'review_answer_colored',
        'last_kyc_data_update',
        'moderationComment',
        'rejectLabels',
        'pretty_data',
    ]
    list_display = [
        'user',
        'applicantId',
        'review_answer_colored',
        'forced_approve',
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user',
        )

    def review_answer_colored(self, obj: UserKYC):
        color = 'darkorange'
        if obj.reviewAnswer == UserKYC.ANSWER_GREEN:
            color = 'green'
        elif obj.reviewAnswer == UserKYC.ANSWER_RED:
            color = 'red'
        ans = obj.reviewAnswer or '-'
        return mark_safe(f'<span style="color:{color}">{ans}</span>')

    review_answer_colored.short_description = 'Review Answer'

    def pretty_data(self, obj: UserKYC):
        if not obj.kyc_data:
            return obj.kyc_data
        return mark_safe(f'<pre>{json.dumps(obj.kyc_data or dict, indent=4, sort_keys=True)}</pre>')

    pretty_data.allow_tags = True
    pretty_data.short_description = "Data"


@admin.register(WithdrawalFee)
class WithdrawalFeeAdmin(BaseModelAdmin):
    list_display = [
        'id',
        'currency',
        'blockchain_currency',
        'address_fee',
    ]
    list_filter = [
        CurrencyFilter,
        ('blockchain_currency', CurrencyFieldFilter)
    ]
    no_delete = False


@admin.register(FeesAndLimits)
class FeesAndLimitsAdmin(BaseModelAdmin):
    no_delete = False
    list_display = [
        'id',
        'currency',
        'limits_deposit_min',
        'limits_deposit_max',
        'limits_withdrawal_min',
        'limits_withdrawal_max',
        'limits_order_min',
        'limits_order_max',
    ]


@admin.register(WalletTransactions)
class WalletTransactionsAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    fields = ('created', 'currency', 'amount', 'fee_amount', 'transaction', 'tx_hash', 'status',
              'state', 'monitoring_state', 'external_accumulation_address',)
    list_display = ('created', 'user', 'currency', 'blockchain', 'amount', 'fee_amount', 'transaction', 'tx_hash',
                    'status', 'state', 'monitoring_state', 'is_old', 'external_accumulation_address',)
    # fields = ('created', 'currency', 'amount', 'tx_hash', 'status', 'state')
    # list_display = ['created', 'user', 'currency', 'blockchain', 'amount', 'tx_amount', 'tx_hash', 'status', 'state']
    list_filter = [
        WalletTransactionStateFilter,
        CurrencyFilter,
        ('wallet__blockchain_currency', CurrencyFieldFilter),
        WalletTransactionStatusFilter,
        ('created', DateRangeFilter),
    ]
    search_fields = [
        'transaction__user__email',
        'transaction__user__id',
        'id',
        'tx_hash'
    ]
    actions = {
        'revert': [],
        'recheck_kyt': [],
        'force_deposit_and_accumulate': [],
        'handle_old_wallet_deposit': [],
        'external_accumulation': [
            {'name': 'external_address', 'type': forms.CharField(), 'default': ''},
        ],
    }

    def get_queryset(self, request):
        qs = super(WalletTransactionsAdmin, self).get_queryset(request).annotate(
            user=F('wallet__user__email'),
            blockchain=F('wallet__blockchain_currency'),
            tx_amount=F('transaction__amount'),
        )
        return qs.prefetch_related('wallet', 'transaction', 'transaction__user')

    # @serial_field(serial_class=CurrencySerialRestField)
    def blockchain(self, obj):
        return obj.blockchain

    def tx_amount(self, obj):
        return obj.tx_amount

    def user(self, obj):
        return obj.user

    def is_old(self, obj):
        return obj.wallet.is_old

    # custom actions
    @admin.action(permissions=('change', ))
    def revert(self, request, queryset):
        """
        :param queryset:
        :type queryset: list[WalletTransactions]
        """
        try:
            with atomic():
                for wallet_tr in queryset:
                    wallet_tr.revert()
        except Exception as e:
            messages.error(request, e)

    @admin.action(permissions=('change',))
    def recheck_kyt(self, request, queryset):
        for entry in queryset:
            entry.check_scoring()
    recheck_kyt.short_description = 'Recheck KYT'

    @admin.action(permissions=('change',))
    def force_deposit_and_accumulate(self, request, queryset: List[WalletTransactions]):
        for wallet_tr in queryset:
            wallet_tr.force_deposit()

    force_deposit_and_accumulate.short_description = 'Force deposit and accumulate'

    @admin.action(permissions=('change',))
    def external_accumulation(self, request, queryset: List[WalletTransactions]):
        data = request.POST or request.data
        address = data.get('external_address')
        for wallet_tr in queryset:
            wallet_tr.set_external_accumulation_address(address)

    external_accumulation.short_description = 'External accumulation'


@admin.register(WalletTransactionsRevert)
class WalletTransactionsRevertAdmin(BaseModelAdmin):
    pass


@admin.register(Exchange)
class ExchangeAdmin(NoAddMixIn, BaseModelAdmin):
    pass


@admin.register(ExecutionResult)
class ExecutionResultAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    pass


@admin.register(OrderChangeHistory)
class OrderChangeHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    pass


@admin.register(OrderStateChangeHistory)
class OrderStateChangeHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    pass


@admin.register(ExternalPricesHistory)
class ExternalPricesHistoryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['created', 'pair', 'price']
    list_filter = [('created', DateRangeFilter), PairsFilter]


@admin.register(TradesAggregatedStats)
class TradesAggregatedStatsAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = [
        'pair',
        'period',
        'ts',
        'min_price',
        'max_price',
        'avg_price',
        'open_price',
        'close_price',
        'volume',
        'amount',
        'num_trades',
        'fee_base',
        'fee_quoted',
    ]
    list_filter = [PairsFilter, ('period', DateRangeFilter), ]


@admin.register(UserPairDailyStat)
class UserPairDailyStatAdmin(BaseModelAdmin):
    pass


@admin.register(WalletHistoryItem)
class WalletHistoryItemAdmin(BaseModelAdmin):
    pass


@admin.register(ExchangeUser)
class ExchangeUserAdmin(ImmutableMixIn, BaseModelAdmin):
    search_fields = ['username', ]
    list_display = ('id', 'date_joined', 'email',  'first_name', 'last_name', 'user_type', 'is_staff', 'is_superuser',
                    'is_active', 'fee', 'kyc', 'kyc_reject_type', 'two_fa',
                    'last_withdrawals', 'orders', 'exchange_fee', 'email_verified', 'phone_verified',)

    fields = (
        'id',
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_superuser',
        'is_active'
    )
    readonly_fields = ['id',]
    ordering = ('-date_joined',)
    actions = [
        'confirm_email',
        'drop_2fa',
        'drop_sms',
    ]
    list_filter = ['profile__user_type', 'userkyc__reviewAnswer', ]
    inlines = [
        BalancesInline,
        OrderInline,
    ]
    no_save = False

    def get_readonly_fields(self, request, obj=None):
        fields = super(ExchangeUserAdmin, self).get_readonly_fields(request, obj=obj)
        is_superuser = request.user.is_superuser
        if 'password' in fields:
            fields.remove('password')
        if not is_superuser:
            fields.extend(['username', 'password', 'email', 'is_staff', 'is_superuser'])
            fields = list(set(fields))
        return fields

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            del actions['delete_selected']
        return actions

    def get_queryset(self, request):
        qs = super(ExchangeUserAdmin, self).get_queryset(request)
        return qs.annotate(
            withdrawals_count=Count('withdrawalrequest', distinct=True),
            orders_count=Count('order', distinct=True),
            two_fa=Case(
                When(twofactorsecrettokens__secret__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField()
            ),
            kyc=Case(
                When(Q(userkyc__forced_approve=True) | Q(userkyc__reviewAnswer=UserKYC.ANSWER_GREEN),
                     then=Value('green')),
                When(userkyc__reviewAnswer=UserKYC.ANSWER_RED, then=Value('red')),
                default=Value('no'),
                output_field=models.CharField(),
            ),
            kyc_reject_type=Case(
                When(userkyc__reviewAnswer=UserKYC.ANSWER_RED, then=F('userkyc__rejectType')),
                default=Value(''),
                output_field=models.CharField(),
            )
        ).prefetch_related('withdrawalrequest_set', 'order_set', 'twofactorsecrettokens_set', 'userkyc')


    def withdrawals_sms_confirmation(self, obj):
        return obj.profile.withdrawals_sms_confirmation

    def fee(self, obj):
        fee = UserFee.objects.filter(user=obj).first()
        fee = fee.fee_rate if (fee and fee.fee_rate) else 0
        return '{}%'.format(fee * 100)

    def exchange_fee(self, obj):
        fee = UserExchangeFee.objects.filter(user=obj).first()
        fee = fee.fee_rate if (fee and fee.fee_rate) else 0
        return '{}%'.format(fee * 100)

    def kyc(self, obj):
        color = 'darkorange'
        if obj.userkyc.reviewAnswer == UserKYC.ANSWER_GREEN:
            color = 'green'
        elif obj.userkyc.reviewAnswer == UserKYC.ANSWER_RED:
            color = 'red'
        ans = obj.userkyc.reviewAnswer or '-'
        return mark_safe(f'<span style="color:{color}">{ans}</span>')

    def last_topups(self, obj):
        qs = Transaction.objects.filter(user=obj, reason__in=[REASON_TOPUP]).order_by('-created')
        count = qs.count()
        if count:
            s_last = '<br>\n'.join(['{} {} ({})'.format(i.amount, i.currency.code, i.created.strftime('%Y.%m.%d')) for i in qs[:1]])
            s = 'Total: &nbsp;&nbsp;{}<br>Last: &nbsp;&nbsp;{}<br><a target="_blank" href="{}?user={}">Show all</a>'.format(
                count,
                s_last,
                reverse('admin:admin_panel_topups_changelist'),
                obj.id)
        else:
            s = 'Total: &nbsp;&nbsp;{}<br><a target="_blank" href="{}?user={}">Show all</a>'.format(
                count,
                reverse('admin:admin_panel_topups_changelist'),
                obj.id)
        return mark_safe(s)

    def last_withdrawals(self, obj):
        qs = Transaction.objects.filter(user=obj, reason__in=[REASON_WITHDRAWAL]).order_by('-created')
        count = qs.count()
        if count:
            s_last = '<br>\n'.join(['{} {} {}'.format(i.created.strftime('%Y.%m.%d %H:%M'), i.amount, i.currency.code) for i in qs[:1]])
            s = 'Total: &nbsp;&nbsp;{}<br>Last: &nbsp;&nbsp;{}<br><a target="_blank" href="{}?reason__in=2,20&user={}">Show all</a>'.format(
                count,
                s_last,
                reverse('admin:admin_panel_transaction_changelist'),
                obj.id)
        else:
            s = 'Total: &nbsp;&nbsp;{}<br><a target="_blank" href="{}?reason__in=2,20&user={}">Show all</a>'.format(
                count,
                reverse('admin:admin_panel_transaction_changelist'),
                obj.id)
        return mark_safe(s)

    def orders(self, obj):
        qs = Order.objects.filter(user=obj, state=ORDER_CLOSED, executed=True)
        s = 'Total closed: &nbsp;&nbsp;{}<br><a target="_blank" href="{}?user={}">Show all orders</a>'.format(
            qs.count(),
            reverse('admin:admin_panel_allorder_changelist'),
            obj.id)
        return mark_safe(s)

    def balances(self, obj):
        s = '\n<br>'.join(['{}: {}'.format(k, v['actual']) for k, v in Balance.for_user(obj).items()])
        return mark_safe(s)

    @admin.display(boolean=True)
    def sof_verified(self, obj):
        return obj.profile.is_sof_verified

    @admin.display(boolean=True)
    def p2p_codes_enabled(self, obj):
        return obj.profile.p2p_codes_enabled

    def status_2FA(self, obj):
        return 'ON' if TwoFactorSecretTokens.is_enabled_for_user(obj) else 'OFF'

    def last_updated_2FA(self, obj):
        return obj.twofactorsecrettokens_set.first().updated

    def kyc_reject_type(self, obj):
        return obj.kyc_reject_type

    def two_fa(self, obj):
        return obj.two_fa

    def withdrawals_count(self, obj):
        return obj.withdrawals_count

    def orders_count(self, obj):
        return obj.orders_count

    @admin.display(boolean=True)
    def email_verified(self, obj):
        exists = EmailAddress.objects.filter(
            user=obj,
            email=obj.email
        ).exists()
        return exists

    @admin.display(boolean=True)
    def phone_verified(self, obj):
        return bool(obj.profile.phone)

    def user_type(self, obj):
        return obj.profile.get_user_type_display()

    @admin.action(description='Confirm email')
    def confirm_email(self, request, queryset):
        for user in queryset:
            ea = EmailAddress.objects.filter(
                user=user,
                email=user.email
            ).first()

            if ea:
                ea.verified = True
                ea.save()

    @admin.action(description='Drop 2FA')
    def drop_2fa(self, request, queryset):
        for user in queryset:
            TwoFactorSecretTokens.drop_for_user(user)

    @admin.action(description='Drop SMS')
    def drop_sms(self, request, queryset):
        for user in queryset:
            user.profile.drop_sms()


@admin.register(Transaction)
class TransactionAdmin(ImmutableMixIn, BaseModelAdmin):
    list_display = ['user', 'created', 'reason', 'currency', 'amount']
    list_filter = ['reason', CurrencyFilter, ('created', DateRangeFilter), ]
    search_fields = ['user__email']
    ordering = ('-created',)


@admin.register(Balance)
class BalanceAdmin(ImmutableMixIn, BaseModelAdmin):
    list_display = ['user', 'currency', 'total', 'free', 'in_orders', 'topup']
    list_filter = [CurrencyFilter]
    search_fields = ['user__email']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            total=Sum(F('amount') + F('amount_in_orders'))
        ).prefetch_related('user')

    def topup(self, obj):
        s = '<a href="{}?reason__in=1,21&user={}">topup</a>'.format(
            reverse('admin:admin_panel_transaction_changelist'),
            obj.user.id)
        return mark_safe(s)

    def in_orders(self, obj):
        return obj.amount_in_orders

    def free(self, obj):
        return obj.amount

    def total(self, obj):
        return obj.total


@admin.register(AllOrder)
class AllOrderAdmin(ReadOnlyMixin, ImmutableMixIn, BaseModelAdmin):
    list_display = ['id', 'user', 'created', 'pair', 'order_operation', 'type', 'quantity',
                    'quantity_left', 'price', 'amount', 'fee', 'stop', 'in_stack',
                    'state_colored', 'executed', 'state_changed_at']
    fields = ['id', 'user', 'pair', 'state', 'stop', 'in_stack', ]
    ordering = ('-created',)
    list_filter = [PairsFilter, 'operation', 'state', 'executed', 'in_stack', OrderTypeFilter, ('created', DateRangeFilter), ]
    actions = [
        'cancel_order',
        # 'revert_orders',
        'revert_orders_balance',
    ]
    search_fields = ['user__email']
    inlines = [HistoryInline]

    def has_delete_permission(self, request, obj=None):
        return BaseModelAdmin.has_delete_permission(self, request, obj=obj)

    def created(self, obj):
        return obj.in_transaction.created

    def amount(self, obj):
        return obj.amount or 0

    def fee(self, obj):
        return obj.fee or 0

    def get_queryset(self, request):
        qs = super(AllOrderAdmin, self).get_queryset(request)
        return qs.prefetch_related(
            'user', 'executionresult_set', 'in_transaction',
        ).annotate(
            fee=Sum('executionresult__fee_amount'),
            amount=F('quantity') * F('price'),
        )

    def order_operation(self, obj):
        if obj.operation == SELL:
            return mark_safe('<span style="color:red">SELL</span>')
        else:
            return mark_safe('<span style="color:green">BUY</span>')

    def state_colored(self, obj):
        color = 'red'
        if obj.state == AllOrder.STATE_OPENED:
            color = 'green'
        elif obj.state == AllOrder.STATE_CANCELLED:
            color = 'darkorange'

        return mark_safe(f'<span style="color:{color}">{obj.get_state_display()}</span>')
    state_colored.short_description = 'State'

    # custom actions
    def cancel_order(self, request, queryset):
        for order in queryset:
            order.delete(by_admin=True)
    cancel_order.short_description = 'Close (cancel) orders'

    # custom actions
    def revert_orders(self, request, queryset):
        with transaction.atomic():
            try:
                for order in queryset:
                    order.revert(check_balance=False)
            except ValidationError as e:
                messages.error(request, e)
    revert_orders.short_description = 'Revert orders'

    # custom actions
    def revert_orders_balance(self, request, queryset):
        try:
            with transaction.atomic():
                queryset: List[Order] = queryset.order_by('id')
                balances = {}
                for order in queryset:
                    balances = order.revert(balances, check_balance=True)
                for u_id, item in balances.items():
                    for cur, amount in item.items():
                        try:
                            currency = Currency.get(cur)
                            if amount < 0:
                                BalanceManager.decrease_amount(u_id, currency, amount)
                            else:
                                BalanceManager.increase_amount(u_id, currency, amount)
                        except NotEnoughFunds as e:
                            raise ValidationError(f'Not enough funds! hold# '
                                                  f'user {u_id}, '
                                                  f'{amount} '
                                                  f'{currency}'
                                                  )
        except ValidationError as e:
            messages.error(request, e)
        except NotEnoughFunds as e:
            messages.error(request, e)

    revert_orders_balance.short_description = 'Revert orders | check balance'


@admin.register(AllOrderNoBot)
class AllOrderNoBotAdmin(AllOrderAdmin):

    def get_queryset(self, request):
        qs = super(AllOrderNoBotAdmin, self).get_queryset(request)
        qs = qs.exclude(user__username__iregex=BOT_RE)
        qs = qs.prefetch_related('user')
        return qs


@admin.register(Topups)
class TopupsAdmin(ReadOnlyMixin, BaseModelAdmin):
    list_display = [
        'user',
        'created',
        'reason',
        'currency',
        'amount',
        'txhash',
        'address']
    list_filter = [TopupReasonFilter, CurrencyFilter, ('created', DateRangeFilter), ]
    search_fields = ['user__email']
    ordering = ('-created',)

    def txhash(self, obj):
        return obj.txhash

    def address(self, obj):
        return obj.address

    def get_queryset(self, request):
        qs = super(TopupsAdmin, self).get_queryset(request)
        qs = qs.filter(reason__in=[REASON_TOPUP,])
        qs = qs.prefetch_related('wallet_transaction').annotate(
            txhash=F('wallet_transaction__tx_hash'))
        qs = qs.prefetch_related('wallet_transaction__wallet').annotate(
            address=F('wallet_transaction__wallet__address'))
        return qs


@admin.register(Match)
class MatchAdmin(ReadOnlyMixin, ImmutableMixIn, BaseModelAdmin):
    list_display = ['created', 'pair', 'user1', 'operation',
                    'user2', 'quantity', 'price', 'total', 'fee', ]
    list_filter = ['order__operation', FeeRateFilter, PairsFilter, ('created', DateRangeFilter), ]
    search_fields = ['order__user__email', 'matched_order__user__email']
    ordering = ('-created',)
    paginator = MyPaginator
    show_full_result_count = False

    readonly_fields = (
        'transaction',
        'user',
        'order',
        'matched_order',
        'cacheback_transaction'
    )

    def operation(self, obj):
        return obj.operation

    def user1(self, obj):
        return obj.user1_name

    def user2(self, obj):
        return obj.user2_name

    def total(self, obj):
        return f'{obj.total:.8f}'

    def fee(self, obj):
        return f'{obj.fee:.2f}%'

    def get_queryset(self, request):
        qs = super(MatchAdmin, self).get_queryset(request)
        qs = qs.filter(cancelled=False)
        qs = qs.select_related('order', 'matched_order')
        return qs.annotate(
            user1_id=F('order__user_id'),
            user2_id=F('matched_order__user_id'),
            user1_name=F('order__user__username'),
            user2_name=F('matched_order__user__username'),
            total=F('quantity') * F('price'),
            fee=F('fee_rate') * Value(100),
            operation=Case(
                When(order__operation=SELL, then=Value('SELL')),
                default=Value('BUY'),
                output_field=models.CharField(),
            )
        )


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = (
        'created', 'user', 'approved', 'confirmed', 'currency', 'blockchain', 'amount',
        'state', 'details', 'sci_gate', 'txid', 'is_freezed',)

    list_filter = [CurrencyFilter, 'state', GateFilter, 'approved', 'confirmed']
    search_fields = ['user__email', 'data__destination']
    ordering = ('-created',)

    actions = [
        'cancel_withdrawal_request',
        'pause',
        'unpause',
        'approve',
        'disable_approve',
        'confirm',
        'unconfirm',
    ]
    global_actions = [
        'export_created_eth',
    ]

    def blockchain(self, obj):
        return obj.data.get('blockchain_currency') or obj.currency.code

    def sci_gate(self, obj):
        if obj.sci_gate_id is not None:
            return GATES[obj.sci_gate_id].NAME
        return ''

    def details(self, obj):
        if obj.sci_gate_id is None:
            return obj.data.get('destination')
        return mark_safe('<br>'.join(f'{k}: {v}' for k, v in obj.data.items()))

    def is_freezed(self, obj):
        return obj.is_freezed

    def get_queryset(self, request):
        qs = super(WithdrawalRequestAdmin, self).get_queryset(request)
        now = timezone.now()
        qs = qs.annotate(
            is_freezed=ExpressionWrapper(
                Q(user__profile__payouts_freezed_till__gt=now),
                output_field=models.BooleanField(),
            )
        )
        return qs.prefetch_related('user', 'user__profile')

    # custom actions
    @admin.action(permissions=('view', 'change',))
    def cancel_withdrawal_request(self, request, queryset):
        try:
            with transaction.atomic():
                for withdrawal_request in queryset:
                    withdrawal_request.cancel()
        except Exception as e:
            messages.error(request, e)

    cancel_withdrawal_request.short_description = 'Cancel'

    @admin.action(permissions=('change',))
    def export_created_eth(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['content-disposition'] = 'attachment; filename=ETH_USDT_{}.csv'.format(
            timezone.now())
        writer = csv.writer(response)
        queryset = queryset.model.objects.filter(
            state=0, confirmed=True, currency__in=['ETH', 'USDT'])
        for obj in queryset:
            row = writer.writerow([obj.id, obj.user.email, obj.data.get(
                'destination'), obj.currency.code, obj.amount])

        return response

    export_created_eth.short_description = 'Export created ETH,USDT withdrawals'

    @admin.action(permissions=('view', 'change',))
    def pause(self, request, queryset):
        for wd in queryset:
            wd.pause()

    pause.short_description = 'Pause'

    @admin.action(permissions=('view', 'change',))
    def unpause(self, request, queryset):
        for wd in queryset:
            wd.unpause()

    unpause.short_description = 'Unpause'

    @admin.action(permissions=('view', 'change',))
    def approve(self, request, queryset):
        for entry in queryset:
            entry.approved = True
            if not entry.confirmed:
                raise ValidationError('Can not approve unconfirmed request!')
            entry.save()

    approve.short_description = 'Approve'

    @admin.action(permissions=('view', 'change',))
    def disable_approve(self, request, queryset):
        for entry in queryset:
            entry.approved = False
            entry.save()

    disable_approve.short_description = 'Disable Approve'

    @admin.action(permissions=('change',))
    def confirm(self, request, queryset):
        for entry in queryset:
            entry.confirmed = True
            entry.save()

    confirm.short_description = 'Confirm'

    @admin.action(permissions=('change',))
    def unconfirm(self, request, queryset):
        for entry in queryset:
            entry.confirmed = False
            entry.save()

    unconfirm.short_description = 'Unconfirm'


@admin.register(UserRestrictions)
class UserRestrictionsAdmin(NoAddMixIn, BaseModelAdmin):
    list_display = [
        'user',
        'disable_topups',
        'disable_withdrawals',
        'disable_orders']
    fields = [
        'user',
        'disable_topups',
        'disable_withdrawals',
        'disable_orders']
    readonly_fields = ['user']
    search_fields = ['user__email']
    ordering = ['-user']


@admin.register(PayGateTopup)
class PayGateTopupAdmin(NoAddMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ('created', 'user', 'currency', 'amount', 'tx_amount',
                    'sci_gate', 'state_colored', 'status_colored',)
    fields = ('tx_link', 'user', 'currency', 'amount', 'tx_amount', 'sci_gate',
              'our_fee_amount', 'state_colored', 'status_colored', 'pretty_data',)
    readonly_fields = ('tx', 'tx_link', 'user', 'currency', 'amount', 'tx_amount', 'state_colored',
                       'status_colored', 'sci_gate', 'our_fee_amount', 'pretty_data',)

    list_filter = [CurrencyFilter, ('created', DateRangeFilter), ]
    search_fields = ['user__email', 'user__id', 'id', ]
    actions = ('revert',)
    ordering = ['-created']

    def tx_amount(self, obj):
        return obj.tx.amount if obj.tx else 0

    def tx_link(self, obj):
        return mark_safe(
            '<a href="%s">%s</a>' % (reverse('admin:admin_panel_topups_change',
                                             args=[obj.tx_id]), obj.tx)
        )

    tx_link.allow_tags = True
    tx_link.short_description = "Transaction"

    def pretty_data(self, obj):
        return mark_safe(
            f'<pre>{json.dumps(obj.data or dict(), indent=4, sort_keys=True)}</pre>')

    pretty_data.allow_tags = True
    pretty_data.short_description = "Data"

    def sci_gate(self, obj):
        if obj.gate_id is not None:
            return GATES[obj.gate_id].NAME
        return ''

    sci_gate.short_description = ugettext_lazy('Gate')

    def state_colored(self, obj):
        color = 'black'
        if obj.state == PayGateTopup.STATE_COMPLETED:
            color = 'green'
        elif obj.state == PayGateTopup.STATE_PENDING:
            color = 'blue'
        elif obj.state == PayGateTopup.STATE_FAILED:
            color = 'red'

        return mark_safe(
            f'<span style="color:{color}">{obj.get_state_display()}</span>')

    state_colored.short_description = ugettext_lazy('State')

    def status_colored(self, obj: PayGateTopup):
        color = 'black'
        if obj.status == PayGateTopup.STATUS_NOT_SET:
            color = 'burlywood'
        elif obj.status == PayGateTopup.STATUS_REVERTED:
            color = 'darkviolet'

        return mark_safe(
            f'<span style="color:{color}">{obj.get_status_display()}</span>')

    status_colored.short_description = ugettext_lazy('Status')

    # custom actions
    @admin.action(permissions=('change', ))
    def revert(self, request, queryset: List[PayGateTopup]):
        try:
            with atomic():
                for pay_gate in queryset:
                    pay_gate.revert()
        except Exception as e:
            messages.error(request, e)


@admin.register(DepositsWithdrawalsStats)
class DepositsWithdrawalsStatsAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ['id', 'created', 'stats', ]
    ordering = ('-created',)
    actions = ['cold_wallet_stats']
    global_actions = ['export_all']

    json_list_fields = {
        'stats': generate_stats_fields()
    }

    @admin.action(permissions=('change',))
    def cold_wallet_stats(self, request, queryset):
        for dw in queryset.order_by('created'):
            calculate_topups_and_withdrawals(dw)
            time.sleep(0.3)

    cold_wallet_stats.short_description = 'Fetch cold wallet stats'

    @admin.action(permissions=('change',), )
    def export_all(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['content-disposition'] = 'attachment; filename=deposits_withdrawals_stats.csv'
        serializer = self.get_serializer(self.get_queryset(request).order_by('-created'), many=True)
        data = serializer.data
        if data:
            writer = csv.DictWriter(response, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
        return response
    export_all.short_description = 'Export All'


@admin.register(DisabledCoin)
class DisabledCoinAdmin(NoAddMixIn, BaseModelAdmin):
    no_delete = False
    list_filter = ['currency'] + DISABLE_COIN_STATES
    list_display = ['currency'] + DISABLE_COIN_STATES
    readonly_fields = ('currency',)


@admin.register(UserWallet)
class UserWalletAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    fields = ['created', 'user', 'currency', 'blockchain_currency', 'address', 'block_type']
    list_display = ['created', 'user', 'currency', 'blockchain_currency', 'address', 'block_type']
    search_fields = ['user__username', 'address']
    list_filter = [CurrencyFilter, ('blockchain_currency', CurrencyFieldFilter), 'block_type']
    actions = ['block_deposits', 'block_accumulations', 'unblock']
    superuser_actions = ['block_deposits', 'block_accumulations', 'unblock']

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            for action, fn in actions:
                if action in self.superuser_actions:
                    del actions[action]
        return actions

    def block_deposits(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_DEPOSIT)
    block_deposits.short_description = 'Block Deposits'

    def block_accumulations(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION)
    block_accumulations.short_description = 'Block Deposits and Accumulations'

    def unblock(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_NOT_BLOCKED)
    unblock.short_description = 'Unblock'


@admin.register(PairSettings)
class PairSettingsAdmin(BaseModelAdmin):
    _fields = ['pair', 'is_enabled', 'is_autoorders_enabled', 'price_source', 'custom_price', 'deviation', 'enable_alerts', 'precisions']
    list_display = _fields
    fields = _fields
    no_delete = False


@admin.register(CoinInfo)
class CoinInfoAdmin(BaseModelAdmin):
    no_delete = False
    list_display = [
        'id',
        'currency',
        'name',
        'is_base',
        'decimals',
        'index',
        'tx_explorer',
    ]

    ordering = ('-id', )


@admin.register(LogEntry)
class LogEntryAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'message')
    filterset_fields = ['action_time', 'action_flag']
    search_fields = ['object_repr', 'user__email']

    def message(self, obj):
        return mark_safe(obj.change_message)


@admin.register(TOTPDevice)
class TOTPDeviceAdmin(BaseModelAdmin):
    no_delete = False
    list_display = ['user', 'name', 'confirmed', 'config_url', 'qrcode_link', ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('user')

        return queryset

    def qrcode_link(self, device):
        try:
            href = reverse('admin:otp_totp_totpdevice_config', kwargs={'pk': device.pk})
            link = format_html('<a href="{}">qrcode</a>', href)
        except Exception:
            link = ''
        return link
    qrcode_link.short_description = "QR Code"

    def qrcode_view(self, request, pk):
        if settings.OTP_ADMIN_HIDE_SENSITIVE_DATA:
            raise PermissionDenied()

        device = TOTPDevice.objects.get(pk=pk)
        if not self.has_view_or_change_permission(request, device):
            raise PermissionDenied()

        try:
            import qrcode
            import qrcode.image.svg

            img = qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgImage)
            response = HttpResponse(content_type='image/svg+xml')
            img.save(response)
        except ImportError:
            response = HttpResponse('', status=503)

        return response