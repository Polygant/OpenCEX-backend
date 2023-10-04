import os

from exchange.settings import env

ADMIN_TOOLS_MENU = 'admin_panel.menu.CustomMenu'
ADMIN_TOOLS_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomIndexDashboard'
ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomAppIndexDashboard'

ENABLE_OTP_ADMIN = True
ADMIN_MASTERPASS = env('ADMIN_MASTERPASS')
ADMIN_BASE_URL = env('ADMIN_BASE_URL', default='control-panel')

VUE_ADMIN_SIDE_MENU = [
    {'icon': 'mdi-view-dashboard', 'text': 'Dashboard', 'link': '/',},
    {'divider': True},
    {'heading': 'Users Management'},
    {'icon': 'mdi-account', 'link': {'name': 'admin_rest_exchangeuser_list'}, 'text': 'Users'},
    {'icon': 'mdi-account', 'link': {'name': 'core_userfee_list'}, 'text': 'Fee Users'},
    {'icon': 'mdi-account-badge-horizontal-outline', 'link': {'name': 'core_userkyc_list'}, 'text': 'User kyc'},
    {'icon': 'mdi-wallet-outline', 'link': {'name': 'core_userwallet_list'}, 'text': 'User Wallets'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_withdrawallimitlevel_list'}, 'text': 'Withdrawal Limit Level'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_withdrawaluserlimit_list'}, 'text': 'Withdrawal User Limit'},
    {'divider': True},
    {'heading': 'Users Trade Info'},
    {'icon': 'mdi-vector-arrange-above', 'link': {'name': 'admin_rest_allordernobot_list'}, 'text': 'All orders no bot'},
    {'icon': 'mdi-vector-arrange-below', 'link': {'name': 'admin_rest_allorder_list'}, 'text': 'All orders'},
    {'icon': 'mdi-piggy-bank', 'link': {'name': 'admin_rest_balance_list'}, 'text': 'Balances'},
    {'icon': 'mdi-vector-combine', 'link': {'name': 'admin_rest_match_list'}, 'text': 'Matches'},
    {'icon': 'mdi-arrow-decision-outline', 'link': {'name': 'admin_rest_transaction_list'}, 'text': 'Transactions'},
    {'icon': 'mdi-account-convert', 'link': {'name': 'admin_rest_userdailystat_list'}, 'text': 'User daily stats'},
    {'icon': 'mdi-menu', 'link': {'name': 'core_difbalance_list'}, 'text': 'Dif balances'},
    {'divider': True},
    {'heading': 'Topups and Withdrawals'},
    {'icon': 'mdi-bank-transfer-out', 'link': {'name': 'admin_rest_withdrawalrequest_list'}, 'text': 'Withdrawal requests'},
    {'icon': 'mdi-bitcoin', 'link': {'name': 'cryptocoins_btcwithdrawalapprove_list'}, 'text': 'BTC Withdrawal Approve'},
    {'icon': 'mdi-ethereum', 'link': {'name': 'cryptocoins_ethwithdrawalapprove_list'}, 'text': 'ETH Withdrawal Approve'},
    {'icon': 'mdi-coins', 'link': {'name': 'cryptocoins_trxwithdrawalapprove_list'}, 'text': 'TRX Withdrawal Approve'},
    {'icon': 'mdi-coins', 'link': {'name': 'cryptocoins_bnbwithdrawalapprove_list'}, 'text': 'BSC Withdrawal Approve'},
    {'icon': 'mdi-coins', 'link': {'name': 'cryptocoins_maticwithdrawalapprove_list'}, 'text': 'Matic Withdrawal Approve'},
    {'icon': 'mdi-bank-transfer-in', 'link': {'name': 'core_wallettransactions_list'}, 'text': 'Crypto TopUps'},
    {'icon': 'mdi-arrow-right-bold-box', 'link': {'name': 'core_paygatetopup_list'}, 'text': 'Paygate TopUps'},
    {'icon': 'mdi-bank-transfer', 'link': {'name': 'cryptocoins_depositswithdrawalsstats_list'}, 'text': 'TopUps and Withdrawals'},
    {'icon': 'mdi-swap-horizontal', 'link': {'name': 'core_inoutsstats_list'}, 'text': 'In/Out Currency Stats'},
    {'divider': True},
    {'heading': 'Coins Management'},
    {'icon': 'mdi-bank-remove', 'link': {'name': 'core_disabledcoin_list'}, 'text': 'Coins Management'},
    {'icon': 'mdi-book-open-outline', 'link': {'name': 'core_coininfo_list'}, 'text': 'Coin Info'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_pairsettings_list'}, 'text': 'Pair Settings'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_pair_list'}, 'text': 'Pairs'},
    {'icon': 'mdi-book-open-outline', 'link': {'name': 'seo_coinstaticpage_list'}, 'text': 'Coin static pages'},
    {'icon': 'mdi-book-open-outline', 'link': {'name': 'seo_coinstaticsubpage_list'}, 'text': 'Coin static sub pages'},
    {'divider': True},
    {'heading': 'Fees and Limits'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_feesandlimits_list'}, 'text': 'Fees And Limits'},
    {'icon': 'mdi-settings-transfer', 'link': {'name': 'core_withdrawalfee_list'}, 'text': 'Withdrawal Fee'},
    {'divider': True},
    {'heading': 'Bots'},
    {'icon': 'mdi-cogs', 'link': {'name': 'bots_botconfig_list'}, 'text': 'Bot configs'},
    {'divider': True},
    {'heading': 'Admin Info'},
    {'icon': 'mdi-incognito', 'link': {'name': 'core_accesslog_list'}, 'text': 'Access logs'},
    {'icon': 'mdi-menu', 'link': {'name': 'admin_logentry_list'}, 'text': 'Admin logs'},
    {'icon': 'mdi-two-factor-authentication', 'link': {'name': 'otp_totp_totpdevice_list'}, 'text': 'TOTP Devices'},
    {'icon': 'mdi-account-group', 'link': {'name': 'auth_group_list'}, 'text': 'Group permissions'},
    {'icon': 'mdi-cog-outline', 'link': {'name': 'core_settings_list'}, 'text': 'Settings'},
    {'icon': 'mdi-incognito', 'link': {'name': 'core_smsconfirmationhistory_list'}, 'text': 'SMS Confirmation History'},
    {'icon': 'mdi-email-edit-outline', 'link': {'name': 'notifications_mailing_list'}, 'text': 'Mailing'},
    {'divider': True},
    {'heading': 'KYT'},
    {'icon': 'mdi-menu', 'link': {'name': 'cryptocoins_scoringsettings_list'}, 'text': 'Scoring Settings'},
    {'icon': 'mdi-menu', 'link': {'name': 'cryptocoins_transactioninputscore_list'}, 'text': 'Transaction Input Score'},
    {'divider': True},
]
