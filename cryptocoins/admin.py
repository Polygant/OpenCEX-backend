from rangefilter.filters import DateRangeFilter

from admin_panel.filters import CurrencyFilter, CurrencyFieldFilter
from core.models import UserWallet
from cryptocoins.models import ScoringSettings
from cryptocoins.models import TransactionInputScore
from django.contrib import admin

from lib.admin import ReadOnlyMixin, BaseModelAdmin, ImmutableMixIn


class BaseWithdrawalApprove(ReadOnlyMixin, BaseModelAdmin):
    list_display = ['user', 'confirmed', 'currency', 'state', 'details', 'amount']
    search_fields = ['user__email', 'data__destination']
    list_filter = [CurrencyFilter]
    global_actions = {
        'process': [{
            'label': 'Password',
            'name': 'key'
        }]
    }

    def details(self, obj):
        return obj.data.get('destination')


@admin.register(TransactionInputScore)
class TransactionInputScoreAdmin(ImmutableMixIn, ReadOnlyMixin, BaseModelAdmin):
    list_display = ('created', 'hash', 'address', 'user', 'score', 'currency',
                    'token_currency', 'deposit_made', 'accumulation_made', 'scoring_state')
    search_fields = ('address', 'hash')
    list_filter = [
        ('created', DateRangeFilter), CurrencyFilter, ('token_currency', CurrencyFieldFilter), 'deposit_made'
    ]
    ordering = ('-created',)

    def user(self, obj):
        wallet = UserWallet.objects.filter(address=obj.address).first()
        if wallet:
            return wallet.user.email
        return None


@admin.register(ScoringSettings)
class ScoringSettingsAdmin(BaseModelAdmin):
    no_delete = False
    vue_resource_extras = {'title': 'Scoring Settings'}
    list_display = ('currency', 'min_score', 'deffered_scoring_time', 'min_tx_amount')
    readonly_fields = ('id',)
