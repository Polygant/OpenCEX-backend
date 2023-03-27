"""
This file was generated with the custommenu management command, it contains
the classes for the admin menu, you can customize this class as you want.

To activate your custom menu add the following to your settings.py::
    ADMIN_TOOLS_MENU = 'oc-backend.menu.CustomMenu'
"""
from exchange.settings import ADMIN_BASE_URL

try:
    # we use django.urls import as version detection as it will fail on django 1.11 and thus we are safe to use
    # gettext_lazy instead of ugettext_lazy instead
    from django.urls import reverse
    from django.utils.translation import gettext_lazy as _
except ImportError:
    from django.core.urlresolvers import reverse
    from django.utils.translation import ugettext_lazy as _

from admin_tools.menu import items, Menu

MENU_ITEMS = [
    items.MenuItem(
        _('Users Management'),
        children=[
            items.MenuItem('Users', f'/{ADMIN_BASE_URL}/admin_panel/exchangeuser/'),
            items.MenuItem('Profiles', f'/{ADMIN_BASE_URL}/core/profile/'),
            items.MenuItem('Email Verify', f'/{ADMIN_BASE_URL}/admin_panel/emailaddressverified/'),
            items.MenuItem('KYC', f'/{ADMIN_BASE_URL}/core/userkyc/'),
            items.MenuItem('Restrictions', f'/{ADMIN_BASE_URL}/core/userrestrictions/'),
            items.MenuItem('Wallets', f'/{ADMIN_BASE_URL}/core/userwallet/'),
        ]
    ),
    items.MenuItem(
        _('Users trade info'),
        children=[
            items.MenuItem('User Balance', f'/{ADMIN_BASE_URL}/admin_panel/balance/'),
            items.MenuItem('User Orders', f'/{ADMIN_BASE_URL}/admin_panel/allordernobot/'),
            items.MenuItem('All Orders', f'/{ADMIN_BASE_URL}/admin_panel/allorder/'),
            items.MenuItem('Matchs', f'/{ADMIN_BASE_URL}/admin_panel/match/'),
            items.MenuItem('Transactions', f'/{ADMIN_BASE_URL}/admin_panel/transaction/'),
            items.MenuItem('Daily Stats', f'/{ADMIN_BASE_URL}/admin_panel/userdailystat/'),
            items.MenuItem('Dif Balance', f'/{ADMIN_BASE_URL}/core/difbalance/'),
            items.MenuItem('Exchange Fee', f'/{ADMIN_BASE_URL}/core/userexchangefee/'),
            items.MenuItem('Fee', f'/{ADMIN_BASE_URL}/core/userfee/'),
        ]
    ),
    items.MenuItem(
        _('Top-ups and Withdrawals'),
        children=[
            items.MenuItem('Withdrawal Requests', f'/{ADMIN_BASE_URL}/admin_panel/withdrawalrequest/'),
            items.MenuItem('Crypto Topups', f'/{ADMIN_BASE_URL}/core/wallettransactions/'),
            items.MenuItem('Paygate Topups', f'/{ADMIN_BASE_URL}/core/paygatetopup/'),
        ]
    ),
    items.MenuItem(
        _('Coins Management'),
        children=[
            items.MenuItem('Info', f'/{ADMIN_BASE_URL}/core/coininfo/'),
            items.MenuItem('Disable', f'/{ADMIN_BASE_URL}/core/disabledcoin/'),
            items.MenuItem('In-Out Stats', f'/{ADMIN_BASE_URL}/core/inoutsstats/'),
            items.MenuItem('T&W Stats', f'/{ADMIN_BASE_URL}/cryptocoins/depositswithdrawalsstats/'),
        ]
    ),
    items.MenuItem(
        _('Fees and Limits'),
        children=[
            items.MenuItem('Fee & Limit', f'/{ADMIN_BASE_URL}/core/feesandlimits/'),
            items.MenuItem('Pair Settings', f'/{ADMIN_BASE_URL}/core/pairsettings/'),
            items.MenuItem('Withdrawal Fee', f'/{ADMIN_BASE_URL}/core/withdrawalfee/'),
            items.MenuItem('Withdrawal Level', f'/{ADMIN_BASE_URL}/core/withdrawallimitlevel/'),
            items.MenuItem('Withdrawal Limit', f'/{ADMIN_BASE_URL}/core/withdrawaluserlimit/'),
        ]
    ),
    items.MenuItem(
        _('Bots'),
        children=[
            items.MenuItem('Settings', f'/{ADMIN_BASE_URL}/bots/botconfig/'),
        ]
    ),
    items.MenuItem(
        _('Admin info'),
        children=[
            items.MenuItem('Admin 2fa', f'/{ADMIN_BASE_URL}/otp_totp/totpdevice/'),
            items.MenuItem('2fa', f'/{ADMIN_BASE_URL}/core/twofactorsecrettokens/'),
            items.MenuItem('2fa logs', f'/{ADMIN_BASE_URL}/core/twofactorsecrethistory/'),
            items.MenuItem('Access Logs', f'/{ADMIN_BASE_URL}/core/accesslog/'),
            items.MenuItem('Entry Logs', f'/{ADMIN_BASE_URL}/admin/logentry/'),
            items.MenuItem('Login Logs', f'/{ADMIN_BASE_URL}/core/loginhistory/'),
            items.MenuItem('Groups', f'/{ADMIN_BASE_URL}/auth/group/'),
            items.MenuItem('Sites', f'/{ADMIN_BASE_URL}/sites/site/'),
            items.MenuItem('Token Proxy', f'/{ADMIN_BASE_URL}/authtoken/tokenproxy/'),
            items.MenuItem('Orders History', f'/{ADMIN_BASE_URL}/core/orderchangehistory/'),
            items.MenuItem('Order State History', f'/{ADMIN_BASE_URL}/core/orderstatechangehistory/'),
            items.MenuItem('Settings', f'/{ADMIN_BASE_URL}/core/settings/'),
        ]
    ),
    items.MenuItem(
        _('KYT'),
        children=[
            items.MenuItem('Score settings', f'/{ADMIN_BASE_URL}/cryptocoins/scoringsettings/'),
            items.MenuItem('Score transaction input', f'/{ADMIN_BASE_URL}/cryptocoins/transactioninputscore/'),
        ]
    ),
    items.MenuItem(
        _('Other'),
        children=[
            items.MenuItem('External Price', f'/{ADMIN_BASE_URL}/core/externalpriceshistory/'),
            items.MenuItem('Exchange List', f'/{ADMIN_BASE_URL}/core/exchange/'),
            items.MenuItem('Sms Confirmation', f'/{ADMIN_BASE_URL}/core/smsconfirmationhistory/'),
            items.MenuItem('Sms', f'/{ADMIN_BASE_URL}/core/smshistory/'),
            items.MenuItem('Trade Aggregated', f'/{ADMIN_BASE_URL}/core/tradesaggregatedstats/'),
            items.MenuItem('Mailing', f'/{ADMIN_BASE_URL}/notifications/mailing/'),
            items.MenuItem('Messages', f'/{ADMIN_BASE_URL}/core/message/'),
            items.MenuItem('Notifications', f'/{ADMIN_BASE_URL}/notifications/notification/'),
        ]
    ),
]


class CustomMenu(Menu):
    """
    Custom Menu for oc-backend admin site.
    """

    def __init__(self, **kwargs):
        Menu.__init__(self, **kwargs)
        self.children += [
            items.MenuItem(_('Dashboard'), reverse('admin:index')),
            items.MenuItem(
                _('Applications'),
                children=MENU_ITEMS,
            ),
            items.MenuItem(
                _('Service'),
                children=[
                    items.MenuItem(
                        _('Withdrawal Approve'),
                        children=[
                            items.MenuItem('Approve BTC', f'/{ADMIN_BASE_URL}/withdrawal_request/approve/btc/'),
                            items.MenuItem('Approve ETH', f'/{ADMIN_BASE_URL}/withdrawal_request/approve/eth/'),
                            items.MenuItem('Approve TRX', f'/{ADMIN_BASE_URL}/withdrawal_request/approve/trx/'),
                            items.MenuItem('Approve BNB', f'/{ADMIN_BASE_URL}/withdrawal_request/approve/bnb/'),
                        ]
                    ),
                    items.MenuItem('Make Topup', f'/{ADMIN_BASE_URL}/make/top-up/'),
                ]
            ),
            items.AppList(
                _('Administration'),
                models=('django.contrib.*',)
            )
        ]

    def init_with_context(self, context):
        """
        Use this method if you need to access the request context.
        """
        return super(CustomMenu, self).init_with_context(context)
