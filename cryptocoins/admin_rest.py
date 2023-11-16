from admin_rest import restful_admin as api_admin
from admin_rest.mixins import ReadOnlyMixin
from admin_rest.restful_admin import DefaultApiAdmin
from core.consts.currencies import BEP20_CURRENCIES, ERC20_MATIC_CURRENCIES
from core.consts.currencies import ERC20_CURRENCIES
from core.consts.currencies import TRC20_CURRENCIES
from core.models import UserWallet
from core.utils.withdrawal import get_withdrawal_requests_to_process
from cryptocoins.coins.bnb import BNB_CURRENCY
from cryptocoins.coins.btc.service import BTCCoinService
from cryptocoins.coins.eth import ETH_CURRENCY
from cryptocoins.coins.matic import MATIC_CURRENCY
from cryptocoins.coins.trx import TRX_CURRENCY
from cryptocoins.models import ScoringSettings
from cryptocoins.models import TransactionInputScore
from cryptocoins.models.proxy import BNBWithdrawalApprove, MaticWithdrawalApprove
from cryptocoins.models.proxy import BTCWithdrawalApprove
from cryptocoins.models.proxy import ETHWithdrawalApprove
from cryptocoins.models.proxy import TRXWithdrawalApprove
from cryptocoins.serializers import BNBKeySerializer
from cryptocoins.serializers import BTCKeySerializer
from cryptocoins.serializers import ETHKeySerializer
from cryptocoins.serializers import TRXKeySerializer
from cryptocoins.serializers import MaticKeySerializer
from cryptocoins.tasks.evm import process_payouts_task


class BaseWithdrawalApprove(ReadOnlyMixin, DefaultApiAdmin):
    list_display = ['user', 'confirmed', 'currency', 'state', 'details', 'amount']
    search_fields = ['user__email', 'data__destination']
    filterset_fields = ['currency']
    global_actions = {
        'process': [{
            'label': 'Password',
            'name': 'key'
        }]
    }

    def details(self, obj):
        return obj.data.get('destination')


@api_admin.register(BTCWithdrawalApprove)
class BTCWithdrawalApproveApiAdmin(BaseWithdrawalApprove):

    def get_queryset(self):
        service = BTCCoinService()
        return service.get_withdrawal_requests()

    @api_admin.action(permissions=True)
    def process(self, request, queryset):
        service = BTCCoinService()
        # form = MySerializer(request)
        serializer = BTCKeySerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            private_key = request.data.get('key')
            service.process_withdrawals(private_key=private_key)

    process.short_description = 'Process withdrawals'


@api_admin.register(ETHWithdrawalApprove)
class ETHWithdrawalApproveApiAdmin(BaseWithdrawalApprove):

    def get_queryset(self):
        return get_withdrawal_requests_to_process([ETH_CURRENCY, *ERC20_CURRENCIES], blockchain_currency='ETH')

    @api_admin.action(permissions=True)
    def process(self, request, queryset):
        serializer = ETHKeySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            password = request.data.get('key')
            process_payouts_task.apply_async(['ETH', password, ], queue='eth_payouts')

    process.short_description = 'Process withdrawals'


@api_admin.register(TRXWithdrawalApprove)
class TRXWithdrawalApproveApiAdmin(BaseWithdrawalApprove):
    def get_queryset(self):
        return get_withdrawal_requests_to_process([TRX_CURRENCY, *TRC20_CURRENCIES], blockchain_currency='TRX')

    @api_admin.action(permissions=True)
    def process(self, request, queryset):
        serializer = TRXKeySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            password = request.data.get('key')
            process_payouts_task.apply_async(['TRX', password, ], queue='trx_payouts')

    process.short_description = 'Process withdrawals'


@api_admin.register(BNBWithdrawalApprove)
class BNBWithdrawalApproveApiAdmin(BaseWithdrawalApprove):
    def get_queryset(self):
        return get_withdrawal_requests_to_process([BNB_CURRENCY, *BEP20_CURRENCIES], blockchain_currency='BNB')

    @api_admin.action(permissions=True)
    def process(self, request, queryset):
        serializer = BNBKeySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            password = request.data.get('key')
            process_payouts_task.apply_async(['BNB', password, ], queue='bnb_payouts')

    process.short_description = 'Process withdrawals'


@api_admin.register(MaticWithdrawalApprove)
class MaticWithdrawalApproveApiAdmin(BaseWithdrawalApprove):
    def get_queryset(self):
        return get_withdrawal_requests_to_process(
            [MATIC_CURRENCY, *ERC20_MATIC_CURRENCIES],
            blockchain_currency='MATIC'
        )

    @api_admin.action(permissions=True)
    def process(self, request, queryset):
        serializer = MaticKeySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            password = request.data.get('key')
            process_payouts_task.apply_async(['MATIC', password, ], queue='matic_payouts')

    process.short_description = 'Process withdrawals'


@api_admin.register(TransactionInputScore)
class TransactionInputScoreAdmin(ReadOnlyMixin, DefaultApiAdmin):
    vue_resource_extras = {'title': 'Transaction Input Score'}
    list_filter = ('deposit_made', 'accumulation_made', 'currency', 'token_currency')
    list_display = ('created', 'hash', 'address', 'user', 'score', 'currency',
                    'token_currency', 'deposit_made', 'accumulation_made', 'scoring_state')
    search_fields = ('address', 'hash')
    filterset_fields = ['created', 'currency', 'token_currency', 'deposit_made']
    ordering = ('-created',)

    def user(self, obj):
        wallet = UserWallet.objects.filter(address=obj.address).first()
        if wallet:
            return wallet.user.email
        return None


@api_admin.register(ScoringSettings)
class ScoringSettingsAdmin(DefaultApiAdmin):
    vue_resource_extras = {'title': 'Scoring Settings'}
    list_display = ('currency', 'min_score', 'deffered_scoring_time', 'min_tx_amount')
    readonly_fields = ('id',)
