import os

from exchange.settings import env

ADMIN_TOOLS_MENU = 'admin_panel.menu.CustomMenu'
ADMIN_TOOLS_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomIndexDashboard'
ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomAppIndexDashboard'

ENABLE_OTP_ADMIN = False
ADMIN_MASTERPASS = env('ADMIN_MASTERPASS')
ADMIN_BASE_URL = env('ADMIN_BASE_URL', default='control-panel')

VUE_ADMIN_SIDE_MENU = [
    {'icon': 'mdi-view-dashboard', 'text': 'Dashboard', 'link': '/',},
    {'divider': True},
    {'icon': 'mdi-account-group', 'model': 'auth.group', 'text': 'Group permissions'},
    {'icon': 'mdi-vector-arrange-above', 'model': 'admin_rest.allordernobot', 'text': 'All orders no bot'},
    {'icon': 'mdi-vector-arrange-below', 'model': 'admin_rest.allorder', 'text': 'All orders'},
    {'icon': 'mdi-piggy-bank', 'model': 'admin_rest.balance', 'text': 'Balances'},
    {'icon': 'mdi-vector-combine', 'model': 'admin_rest.match', 'text': 'Matches'},
    {'icon': 'mdi-account', 'model': 'auth.user', 'text': 'Users'},
    {'icon': 'mdi-account', 'model': 'core.userfee', 'text': 'Fee Users'},
    {'icon': 'mdi-account-badge-horizontal-outline', 'model': 'core.userkyc', 'text': 'User kyc'},
    {'icon': 'mdi-arrow-decision-outline', 'model': 'admin_rest.transaction', 'text': 'Transactions'},
    {'icon': 'mdi-account-convert', 'model': 'admin_rest.userdailystat', 'text': 'User daily stats'},
    {'icon': 'mdi-bank-remove', 'model': 'core.disabledcoin', 'text': 'Coins Management'},
    {'icon': 'mdi-book-open-outline', 'model': 'core.coininfo', 'text': 'Coin Info'},
    {'icon': 'mdi-book-open-outline', 'model': 'seo.coinstaticpage', 'text': 'Coin static pages'},
    {'icon': 'mdi-book-open-outline', 'model': 'seo.coinstaticsubpage', 'text': 'Coin static sub pages'},
    {'icon': 'mdi-email-edit-outline', 'model': 'notifications.mailing', 'text': 'Mailing'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.feesandlimits', 'text': 'Fees And Limits'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.withdrawalfee', 'text': 'Withdrawal Fee'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.withdrawallimitlevel', 'text': 'Withdrawal Limit Level'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.withdrawaluserlimit', 'text': 'Withdrawal User Limit'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.pairsettings', 'text': 'Pair Settings'},
    {'icon': 'mdi-settings-transfer', 'model': 'core.pair', 'text': 'Pairs'},
    {'icon': 'mdi-bank-transfer', 'model': 'cryptocoins.depositswithdrawalsstats', 'text': 'TopUps and Withdrawals'},
    {'icon': 'mdi-swap-horizontal', 'model': 'core.inoutsstats', 'text': 'In/Out Currency Stats'},
    {'icon': 'mdi-incognito', 'model': 'core.accesslog', 'text': 'Access logs'},
    {'icon': 'mdi-wallet-outline', 'model': 'core.userwallet', 'text': 'User Wallets'},
    {'icon': 'mdi-menu', 'model': 'core.difbalance', 'text': 'Dif balances'},
    {'divider': True},
    {'heading': 'menu.withdrawals'},
    {'icon': 'mdi-bank-transfer-out', 'model': 'admin_rest.withdrawalrequest', 'text': 'Withdrawal requests'},
    {'icon': 'mdi-bitcoin', 'model': 'cryptocoins.btcwithdrawalapprove', 'text': 'BTC Withdrawal Approve'},
    {'icon': 'mdi-ethereum', 'model': 'cryptocoins.ethwithdrawalapprove', 'text': 'ETH Withdrawal Approve'},
    {'icon': 'mdi-coins', 'model': 'cryptocoins.trxwithdrawalapprove', 'text': 'TRX Withdrawal Approve'},
    {'icon': 'mdi-coins', 'model': 'cryptocoins.bnbwithdrawalapprove', 'text': 'BSC Withdrawal Approve'},
    {'divider': True},
    {'heading': 'menu.topups'},
    {'icon': 'mdi-bank-transfer-in', 'model': 'core.wallettransactions', 'text': 'Crypto TopUps'},
    {'icon': 'mdi-arrow-right-bold-box', 'model': 'core.paygatetopup', 'text': 'Paygate TopUps'},
    {'divider': True},
    {'heading': 'menu.bots'},
    {'icon': 'mdi-cogs', 'model': 'bots.botconfig', 'text': 'Bot configs'},
    {'divider': True},
    {'heading': 'menu.otp'},
    {'icon': 'mdi-two-factor-authentication', 'model': 'otp_totp.totpdevice', 'text': 'TOTP Devices'},
    {'divider': True},
    {'heading': 'Scoring'},
    {'icon': 'mdi-menu', 'model': 'cryptocoins.scoringsettings', 'text': 'Scoring Settings'},
    {'icon': 'mdi-menu', 'model': 'cryptocoins.transactioninputscore', 'text': 'Transaction Input Score'},
    {'divider': True},
    {'heading': 'Admin Logs'},
    {'icon': 'mdi-menu', 'model': 'admin.logentry', 'text': 'Admin logs'},
    {'divider': True},
    {'heading': 'Settings'},
    {'icon': 'mdi-cog-outline', 'model': 'core.settings', 'text': 'Settings'},
    {'icon': 'mdi-incognito', 'model': 'core.smsconfirmationhistory', 'text': 'SMS Confirmation History'},
]

