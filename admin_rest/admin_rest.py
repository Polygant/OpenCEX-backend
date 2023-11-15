import csv
import json
import logging
import time
from collections import defaultdict
from typing import List

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User, Group
from django.db import transaction, models
from django.db.models import F, OuterRef, Subquery, Sum, Count, When, Value, Case, ExpressionWrapper
from django.db.models import Q
from django.db.transaction import atomic
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy
from django_otp.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import ValidationError

from admin_rest import restful_admin as api_admin
from admin_rest.fields import BooleanReadOnlyField, WithdrawalSmsConfirmationField, serial_field, \
    CurrencySerialRestField
from admin_rest.mixins import JsonListApiViewMixin
from admin_rest.mixins import NoDeleteMixin, NoCreateMixin
from admin_rest.mixins import ReadOnlyMixin
from admin_rest.models import AllOrder, ExchangeUser
from admin_rest.models import AllOrderNoBot
from admin_rest.models import Balance
from admin_rest.models import Match
from admin_rest.models import Topups
from admin_rest.models import Transaction
from admin_rest.models import UserDailyStat
from admin_rest.models import WithdrawalRequest
from admin_rest.permissions import IsSuperAdminUser
from admin_rest.restful_admin import DefaultApiAdmin
from admin_rest.restful_admin import RestFulModelAdmin
from admin_rest.utils import get_bots_ids
from core.balance_manager import BalanceManager
from core.consts.inouts import DISABLE_COIN_STATES
from core.consts.orders import SELL
from core.currency import Currency
from core.exceptions.inouts import NotEnoughFunds
from core.models import PairSettings
from core.models.cryptocoins import UserWallet
from core.models.facade import AccessLog, CoinInfo
from core.models.facade import LoginHistory
from core.models.facade import Message
from core.models.facade import Profile
from core.models.facade import SmsHistory
from core.models.facade import SourceOfFunds
from core.models.facade import TwoFactorSecretHistory
from core.models.facade import TwoFactorSecretTokens
from core.models.facade import UserExchangeFee
from core.models.facade import UserFee
from core.models.facade import UserKYC
from core.models.facade import UserRestrictions
from core.models.inouts.dif_balance import DifBalance
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.fees_and_limits import WithdrawalFee
from core.models.inouts.pair import Pair
from core.models.inouts.sci import GATES
from core.models.inouts.sci import PayGateTopup
from core.models.inouts.transaction import REASON_MANUAL_TOPUP
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.wallet import WalletTransactionsRevert
from core.models.orders import Exchange
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.models.orders import OrderChangeHistory
from core.models.orders import OrderStateChangeHistory
from core.models.stats import ExternalPricesHistory
from core.models.stats import TradesAggregatedStats
from core.models.stats import UserPairDailyStat
from core.models.wallet_history import WalletHistoryItem
from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
from cryptocoins.models.stats import DepositsWithdrawalsStats
from cryptocoins.tasks import calculate_topups_and_withdrawals
from cryptocoins.utils.stats import generate_stats_fields
from lib.helpers import BOT_RE

log = logging.getLogger(__name__)


@api_admin.register(DifBalance)
class DifBalanceAdmin(ReadOnlyMixin, DefaultApiAdmin):
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


@api_admin.register(EmailAddress)
class EmailConfirmationApiAdmin(NoCreateMixin, NoDeleteMixin, DefaultApiAdmin):
    list_display = ['verified']


@api_admin.register(Group)
class GroupApiAdmin(DefaultApiAdmin):
    fields = ['name', 'permissions', 'users']
    list_display = ['name']

    def permissions(self, obj):
        perms = defaultdict(dict)
        for perm in obj.permissions.all():
            name = f'{perm.content_type.app_label}/{perm.content_type.model}'
            action = perm.codename.split('_')[0]
            perms[name][action] = True

        ret_perms = [{
            'name': key,
            'permissions': value
        } for key, value in perms.items()]
        ret_perms = sorted(ret_perms, key=lambda i: i['name'])
        return ret_perms

    def users(self, obj):
        return list(obj.user_set.values('id', 'username', 'email'))


@api_admin.register(AccessLog)
class AccessLogApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
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


@api_admin.register(LoginHistory)
class LoginHistoryApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['created', 'ip', 'user_agent']
    readonly_fields = ['created', 'ip', 'user_agent']
    ordering = ('-created',)


@api_admin.register(Message)
class MessageApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(Profile)
class ProfileApiAdmin(DefaultApiAdmin):
    vue_resource_extras = {'aside': {'edit': True}}
    readonly_fields = (
        'id',
        'created',
        'updated',
        'affiliate_code',
        'register_ip')

    def country(self, obj):
        return obj.country.code


@api_admin.register(SmsHistory)
class SmsHistoryApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['user', 'created', 'phone', 'withdrawals_sms_confirmation']
    filterset_fields = ['created']
    search_fields = ['user__email', 'phone']
    ordering = ('-created',)


@api_admin.register(SourceOfFunds)
class SourceOfFundsApiAdmin(DefaultApiAdmin):
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


@api_admin.register(TwoFactorSecretHistory)
class TwoFactorSecretHistoryApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    fields = ['created', 'status']
    readonly_fields = ['created', 'status']
    ordering = ('-created',)


@api_admin.register(TwoFactorSecretTokens)
class TwoFactorSecretTokensApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
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

    @api_admin.action(permissions=('change',))
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


@api_admin.register(UserExchangeFee)
class UserExchangeFeeApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(UserFee)
class UserFeeApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(UserKYC)
class UserKYCApiAdmin(NoCreateMixin, DefaultApiAdmin):
    search_fields = ['user__email']


@api_admin.register(WithdrawalFee)
class WithdrawalFeeApiAdmin(DefaultApiAdmin):
    list_display = [
        'id',
        'currency',
        'blockchain_currency',
        'address_fee',
    ]
    filterset_fields = ['currency', 'blockchain_currency']


@api_admin.register(FeesAndLimits)
class FeesAndLimitsApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(WalletTransactions)
class WalletTransactionsApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    # list_filter = ['state', 'currency', 'status', 'created', AddressTypeFilter]
    fields = ('created', 'user', 'currency', 'blockchain', 'amount', 'tx_amount', 'tx_hash', 'status', 'state')
    list_display = ['created', 'user', 'currency', 'blockchain', 'amount', 'tx_amount', 'tx_hash', 'status', 'state']
    filterset_fields = [
        'state',
        'currency',
        'wallet__blockchain_currency',
        'status',
        'created']
    search_fields = [
        'transaction__user__email',
        'transaction__user__id',
        'id',
        'tx_hash']

    actions = {
        'revert': [],
        'recheck_kyt': [],
        'force_deposit_and_accumulate': [],
        'external_accumulation': [
            {'label': 'External address', 'name': 'external_address'},
        ],
    }

    def get_queryset(self):
        qs = super(WalletTransactionsApiAdmin, self).get_queryset().annotate(
            user=F('wallet__user__email'),
            blockchain=F('wallet__blockchain_currency'),
            tx_amount=F('transaction__amount'),
        )
        return qs

    @serial_field(serial_class=CurrencySerialRestField)
    def blockchain(self, obj):
        return obj.blockchain

    def tx_amount(self, obj):
        return obj.tx_amount

    def user(self, obj):
        return obj.user

    # custom actions
    @api_admin.action(permissions=True)
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

    @api_admin.action(permissions=('change',))
    def recheck_kyt(self, request, queryset):
        for entry in queryset:
            entry.check_scoring()

    recheck_kyt.short_description = 'Recheck KYT'

    @api_admin.action(permissions=('change',))
    def force_deposit_and_accumulate(self, request, queryset: List[WalletTransactions]):
        for wallet_tr in queryset:
            wallet_tr.force_deposit()

    force_deposit_and_accumulate.short_description = 'Force deposit and accumulate'

    @api_admin.action(permissions=('change',))
    def external_accumulation(self, request, queryset: List[WalletTransactions]):
        data = request.POST or request.data
        address = data.get('external_address')
        for wallet_tr in queryset:
            wallet_tr.set_external_accumulation_address(address)

    external_accumulation.short_description = 'External accumulation'


@api_admin.register(WalletTransactionsRevert)
class WalletTransactionsRevertApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(Exchange)
class ExchangeApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(ExecutionResult)
class ExecutionResultApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(OrderChangeHistory)
class OrderChangeHistoryApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    pass


@api_admin.register(OrderStateChangeHistory)
class OrderStateChangeHistoryApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(ExternalPricesHistory)
class ExternalPricesHistoryApiAdmin(DefaultApiAdmin):
    list_display = ['created', 'pair', 'price']
    filterset_fields = ['created', 'pair']


@api_admin.register(TradesAggregatedStats)
class TradesAggregatedStatsApiAdmin(DefaultApiAdmin):
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
    readonly_fields = list_display
    filterset_fields = ['pair', 'period']


@api_admin.register(UserPairDailyStat)
class UserPairDailyStatApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(WalletHistoryItem)
class WalletHistoryItemApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(User)
class UserApiAdmin(DefaultApiAdmin, ReadOnlyMixin):
    list_display = ('id', 'date_joined', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')
    fields = ('id', 'date_joined', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ['username']
    ordering = ('-date_joined',)



@api_admin.register(ExchangeUser)
class ExchangeUserApiAdmin(NoCreateMixin, DefaultApiAdmin):
    vue_resource_extras = {'aside': {'edit': True}}
    list_display = ('id', 'date_joined', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active',
                    'user_type', 'kyc', 'kyc_reject_type', 'two_fa',
                    'withdrawals_count', 'orders_count',
                    'email_verified', 'withdrawals_sms_confirmation',
                    )
    fields = (
        'id',
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_superuser',
        'is_active',
    )
    readonly_fields = [
        'id',
        'is_superuser',
        'is_staff',
        'user_type',
        'two_fa',
        'email_verified',
        'withdrawals_count',
        'orders_count',
        'kyc',
        'kyc_reject_type',
    ]
    search_fields = ['username']
    ordering = ('-date_joined',)
    actions = {
        'confirm_email': [],
        'topup': [
            {'label': 'Amount', 'name': 'amount', 'type': 'decimal', },
            {'label': 'Currency', 'name': 'currency', },
            {'label': 'Password', 'name': 'password', },
        ],
        'drop_2fa': [],
        'drop_sms': []
    }
    filterset_fields = ['profile__user_type', ]

    def get_queryset(self):
        qs = super(ExchangeUserApiAdmin, self).get_queryset()
        return qs.annotate(
            withdrawals_sms_confirmation=F("profile__withdrawals_sms_confirmation"),
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
            ),
            email_verified=Case(
                When(
                    Subquery(
                        EmailAddress.objects.filter(
                            user_id=OuterRef("id"),
                            email=OuterRef("email")
                        ).values("verified")
                    ), then=Value(True)
                ),
                default=Value(False),
                output_field=models.BooleanField(),
            ),
        )

    def kyc(self, obj):
        return obj.kyc

    def kyc_reject_type(self, obj):
        return obj.kyc_reject_type

    @serial_field(serial_class=BooleanReadOnlyField)
    def two_fa(self, obj):
        return obj.two_fa

    def withdrawals_count(self, obj):
        return obj.withdrawals_count

    def orders_count(self, obj):
        return obj.orders_count

    @serial_field(serial_class=BooleanReadOnlyField)
    def email_verified(self, obj):
        return obj.email_verified

    def user_type(self, obj):
        return obj.profile.get_user_type_display()

    @serial_field(serial_class=WithdrawalSmsConfirmationField)
    def withdrawals_sms_confirmation(self, obj):
        return obj.withdrawals_sms_confirmation

    @api_admin.action(permissions=[IsSuperAdminUser])
    def topup(self, request, queryset):
        currency = request.data.get('currency')
        amount = request.data.get('amount')
        password = request.data.get('password')
        if not currency or not amount:
            raise ValidationError('Currency or amount incorrect!')
        if password != settings.ADMIN_MASTERPASS:
            raise ValidationError('Incorrect password!')

        currency = Currency.get(currency)
        for user in queryset:
            with atomic():
                tx = Transaction.topup(user.id, currency, amount, {'1': 1}, reason=REASON_MANUAL_TOPUP)
                create_or_update_wallet_history_item_from_transaction(tx)

    topup.short_description = 'Make Topup'

    @api_admin.action(permissions=True)
    def confirm_email(self, request, queryset):
        for user in queryset:
            ea = EmailAddress.objects.filter(
                user=user,
                email=user.email
            ).first()

            if ea:
                ea.verified = True
                ea.save()

    confirm_email.short_description = 'Confirm email'

    @api_admin.action(permissions=True)
    def drop_2fa(self, request, queryset):
        for user in queryset:
            TwoFactorSecretTokens.drop_for_user(user)
    drop_2fa.short_description = 'Drop 2FA'

    @api_admin.action(permissions=True)
    def drop_sms(self, request, queryset):
        for user in queryset:
            user.profile.drop_sms()
    drop_sms.short_description = 'Drop SMS'


@api_admin.register(Transaction)
class TransactionApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['user', 'created', 'reason', 'currency', 'amount', 'state']
    filterset_fields = ['reason', 'currency', 'created', 'state',]
    search_fields = ['user__email']
    ordering = ('-created',)


@api_admin.register(Balance)
class BalanceApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    vue_resource_extras = {'searchable_fields': ['user']}
    list_display = ['user', 'currency', 'total', 'amount', 'amount_in_orders']
    filterset_fields = ['currency']
    search_fields = ['user__email']

    def get_queryset(self):
        qs = super(BalanceApiAdmin, self).get_queryset()
        return qs.annotate(
            total=Sum(F('amount') + F('amount_in_orders'))
        ).prefetch_related('user')

    def total(self, obj):
        return obj.total


@api_admin.register(AllOrder)
class AllOrderApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['id', 'user', 'created', 'pair', 'operation', 'type', 'quantity',
                    'quantity_left', 'price', 'amount', 'fee', 'state', 'executed',
                    'state_changed_at']
    fields = ['id', 'user', 'pair', 'state']
    ordering = ('-created',)
    filterset_fields = ['pair', 'operation', 'state', 'executed', 'created']
    actions = [
        'cancel_order',
        # 'revert_orders',
        'revert_orders_balance',
    ]
    search_fields = ['user__email']

    def created(self, obj):
        return obj.in_transaction.created

    def amount(self, obj):
        return obj.amount or 0

    def fee(self, obj):
        return obj.fee or 0

    def get_queryset(self):
        qs = super(AllOrderApiAdmin, self).get_queryset()
        return qs.prefetch_related(
            'user', 'executionresult_set', 'in_transaction',
        ).annotate(
            fee=Sum('executionresult__fee_amount'),
            amount=F('quantity') * F('price'),
        )

    # custom actions
    @api_admin.action(permissions=True)
    def cancel_order(self, request, queryset):
        for order in queryset:
            order.delete(by_admin=True)
    cancel_order.short_description = 'Close (cancel) orders'

    @api_admin.action(permissions=True)
    def revert_orders(self, request, queryset):
        with transaction.atomic():
            try:
                for order in queryset:
                    order.revert(check_balance=False)
            except ValidationError as e:
                messages.error(request, e)
    revert_orders.short_description = 'Revert orders'

    @api_admin.action(permissions=True)
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
                                BalanceManager.decrease_amount(
                                    u_id, currency, amount)
                            else:
                                BalanceManager.increase_amount(
                                    u_id, currency, amount)
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
    revert_orders_balance.short_description = 'Revert orders balance'


@api_admin.register(AllOrderNoBot)
class AllOrderNoBotApiAdmin(AllOrderApiAdmin):

    def get_queryset(self):
        qs = super(AllOrderNoBotApiAdmin, self).get_queryset()
        qs = qs.exclude(user__username__iregex=BOT_RE)
        return qs


@api_admin.register(Topups)
class TopupsApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = [
        'user',
        'created',
        'reason',
        'currency',
        'amount',
        'txhash',
        'address']
    # list_filter = [TopupReasonFilter, CurrencyFilter, ('created', DateRangeFilter), ]
    filterset_fields = ['currency', 'reason', 'created']
    search_fields = ['user__email']
    ordering = ('-created',)

    def txhash(self, obj):
        return obj.txhash

    def address(self, obj):
        return obj.address

    def get_queryset(self):
        qs = super(TopupsApiAdmin, self).get_queryset()
        qs = qs.filter(reason__in=[REASON_TOPUP,])
        qs = qs.prefetch_related('wallet_transaction').annotate(
            txhash=F('wallet_transaction__tx_hash'))
        qs = qs.prefetch_related('wallet_transaction__wallet').annotate(
            address=F('wallet_transaction__wallet__address'))
        return qs


@api_admin.register(Match)
class MatchApiAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['created', 'pair', 'user1', 'operation',
                    'user2', 'quantity', 'price', 'total', 'fee', ]
    filterset_fields = ['order__operation', 'pair', 'created']
    search_fields = ['order__user__email', 'matched_order__user__email']
    ordering = ('-created',)

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

    def get_queryset(self):
        bots_ids = get_bots_ids()
        qs = super(MatchApiAdmin, self).get_queryset()
        qs = qs.filter(cancelled=False)
        qs = qs.select_related('order', 'matched_order')
        qs = qs.annotate(
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
        qs = qs.filter(~Q(Q(user1_id__in=bots_ids) & Q(user2_id__in=bots_ids)))

        return qs


# TODO optimize
@api_admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(ReadOnlyMixin, RestFulModelAdmin):
    list_display = (
        'created', 'user', 'approved', 'confirmed', 'currency', 'blockchain', 'amount',
        'state', 'details', 'sci_gate', 'txid', 'is_freezed',)

    filterset_fields = ['currency', 'approved', 'confirmed', 'state']
    search_fields = ['user__email', 'data__destination']
    ordering = ('-created', )
    readonly_fields = [
        'created', 'user', 'currency', 'blockchain', 'amount', 'state', 'details', 'sci_gate', 'txid', 'is_freezed',
    ]
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

    def get_queryset(self):
        qs = super(WithdrawalRequestAdmin, self).get_queryset()
        now = timezone.now()
        qs = qs.annotate(
            is_freezed=ExpressionWrapper(
                Q(user__profile__payouts_freezed_till__gt=now),
                output_field=models.BooleanField(),
            )
        )
        return qs.prefetch_related('user', 'user__profile')

    # custom actions
    @api_admin.action(permissions=('view', 'change',))
    def cancel_withdrawal_request(self, request, queryset):
        try:
            with transaction.atomic():
                for withdrawal_request in queryset:
                    withdrawal_request.cancel()
        except Exception as e:
            messages.error(request, e)
    cancel_withdrawal_request.short_description = 'Cancel'

    @api_admin.action(permissions=('change',), custom_response=True)
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

    @api_admin.action(permissions=('view', 'change',))
    def pause(self, request, queryset):
        for wd in queryset:
            wd.pause()
    pause.short_description = 'Pause'

    @api_admin.action(permissions=('view', 'change',))
    def unpause(self, request, queryset):
        for wd in queryset:
            wd.unpause()
    unpause.short_description = 'Unpause'

    @api_admin.action(permissions=('view', 'change',))
    def approve(self, request, queryset):
        for entry in queryset:
            entry.approved = True
            if not entry.confirmed:
                raise ValidationError('Can not approve unconfirmed request!')
            entry.save()
    approve.short_description = 'Approve'

    @api_admin.action(permissions=('view', 'change',))
    def disable_approve(self, request, queryset):
        for entry in queryset:
            entry.approved = False
            entry.save()
    disable_approve.short_description = 'Disable Approve'

    @api_admin.action(permissions=('change',))
    def confirm(self, request, queryset):
        for entry in queryset:
            entry.confirmed = True
            entry.save()

    confirm.short_description = 'Confirm'

    @api_admin.action(permissions=('change',))
    def unconfirm(self, request, queryset):
        for entry in queryset:
            entry.confirmed = False
            entry.save()

    unconfirm.short_description = 'Unconfirm'


@api_admin.register(UserDailyStat)
class UserPairDailyStatAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['user', 'pair', 'day', 'currency1', 'currency2', 'volume_got1', 'volume_got2',
                    'fee_amount_paid1', 'fee_amount_paid2', 'volume_spent1', 'volume_spent2']
    readonly_fields = list_display
    filterset_fields = ['day', 'pair', 'currency1', 'currency2']
    search_fields = ['user__email']

    def get_queryset(self):
        qs = super(UserPairDailyStatAdmin, self).get_queryset()
        return qs.exclude(fee_amount_paid1=0, fee_amount_paid2=0)


@api_admin.register(UserRestrictions)
class UserRestrictionsAdmin(DefaultApiAdmin):
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


@api_admin.register(PayGateTopup)
class PayGateTopupAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ('created', 'user', 'currency', 'amount', 'tx_amount',
                    'sci_gate', 'state_colored', 'status_colored',)
    fields = ('tx_link', 'user', 'currency', 'amount', 'tx_amount', 'sci_gate',
              'our_fee_amount', 'state_colored', 'status_colored', 'pretty_data',)
    readonly_fields = ('tx', 'tx_link', 'user', 'currency', 'amount', 'tx_amount', 'state_colored',
                       'status_colored', 'sci_gate', 'our_fee_amount', 'pretty_data',)

    filterset_fields = ['currency', 'created']
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
    @api_admin.action(permissions=True)
    def revert(self, request, queryset: List[PayGateTopup]):
        try:
            with atomic():
                for pay_gate in queryset:
                    pay_gate.revert()
        except Exception as e:
            messages.error(request, e)


@api_admin.register(DepositsWithdrawalsStats)
class DepositsWithdrawalsStatsAdmin(JsonListApiViewMixin, ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['created', ]
    ordering = ('-created',)
    actions = ['cold_wallet_stats']
    global_actions = ['export_all']

    json_list_fields = {
        'stats': generate_stats_fields()
    }

    @api_admin.action(permissions=True)
    def cold_wallet_stats(self, request, queryset):
        for dw in queryset.order_by('created'):
            calculate_topups_and_withdrawals(dw)
            time.sleep(0.3)

    cold_wallet_stats.short_description = 'Fetch cold wallet stats'

    @api_admin.action(permissions=True, custom_response=True)
    def export_all(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['content-disposition'] = 'attachment; filename=deposits_withdrawals_stats.csv'
        serializer = self.get_serializer(self.get_queryset().order_by('-created'), many=True)
        data = serializer.data
        if data:
            writer = csv.DictWriter(response, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
        return response
    export_all.short_description = 'Export All'


@api_admin.register(DisabledCoin)
class DisabledInoutCoinAdmin(NoCreateMixin, DefaultApiAdmin):
    list_filter = ['currency'] + DISABLE_COIN_STATES
    list_display = ['currency'] + DISABLE_COIN_STATES
    readonly_fields = ('currency',)


@api_admin.register(UserWallet)
class UserWalletAdmin(ReadOnlyMixin, DefaultApiAdmin):
    fields = ['created', 'user', 'currency', 'blockchain_currency', 'address', 'block_type']
    list_display = ['created', 'user', 'currency', 'blockchain_currency', 'address', 'block_type']
    search_fields = ['user__username', 'address']
    filterset_fields = ['currency', 'blockchain_currency', 'block_type']


    actions = ['block_deposits', 'block_accumulations', 'unblock']

    @api_admin.action(permissions=[IsSuperAdminUser])
    def block_deposits(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_DEPOSIT)
    block_deposits.short_description = 'Block Deposits'

    @api_admin.action(permissions=[IsSuperAdminUser])
    def block_accumulations(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION)
    block_accumulations.short_description = 'Block Deposits and Accumulations'

    @api_admin.action(permissions=[IsSuperAdminUser])
    def unblock(self, request, queryset):
        queryset.update(block_type=UserWallet.BLOCK_TYPE_NOT_BLOCKED)
    unblock.short_description = 'Unblock'


@api_admin.register(PairSettings)
class PairSettingsAdmin(DefaultApiAdmin):
    _fields = ['pair', 'is_enabled', 'is_autoorders_enabled', 'price_source', 'custom_price',
               'deviation', 'precisions', 'min_order_size', 'min_base_amount_increment', 'min_price_increment']
    list_display = _fields
    fields = _fields


@api_admin.register(Pair)
class PairAdmin(DefaultApiAdmin):
    _fields = ['base', 'quote']
    list_display = _fields
    fields = _fields


@api_admin.register(CoinInfo)
class CoinInfoAdmin(DefaultApiAdmin):
    pass


@api_admin.register(LogEntry)
class LogEntryAdmin(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'message')
    filterset_fields = ['action_time', 'action_flag']
    search_fields = ['object_repr', 'user__email']

    def message(self, obj):
        return mark_safe(obj.change_message)



@api_admin.register(TOTPDevice)
class TOTPDeviceAdmin(DefaultApiAdmin):
    list_display = ['user', 'name', 'confirmed', 'config_url']

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.select_related('user')

        return queryset

    # def qrcode_link(self, device):
    #     try:
    #         href = reverse('admin:otp_totp_totpdevice_config', kwargs={'pk': device.pk})
    #         link = format_html('<a href="{}">qrcode</a>', href)
    #     except Exception:
    #         link = ''
    #     return link
    # qrcode_link.short_description = "QR Code"

    # # custom actions
    # @api_admin.action(permissions=True)
    # def revert(self, request, queryset):
    #
    # def qrcode_view(self, request, pk):
    #     if settings.OTP_ADMIN_HIDE_SENSITIVE_DATA:
    #         raise PermissionDenied()
    #
    #     device = TOTPDevice.objects.get(pk=pk)
    #     if not self.has_view_or_change_permission(request, device):
    #         raise PermissionDenied()
    #
    #     try:
    #         import qrcode
    #         import qrcode.image.svg
    #
    #         img = qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgImage)
    #         response = HttpResponse(content_type='image/svg+xml')
    #         img.save(response)
    #     except ImportError:
    #         response = HttpResponse('', status=503)
    #
    #     return response




