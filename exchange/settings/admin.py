import os

from exchange.settings import env

ADMIN_TOOLS_MENU = 'admin_panel.menu.CustomMenu'
ADMIN_TOOLS_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomIndexDashboard'
ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'admin_panel.dashboard.CustomAppIndexDashboard'

ENABLE_OTP_ADMIN = True
ADMIN_MASTERPASS = env('ADMIN_MASTERPASS')
ADMIN_BASE_URL = env('ADMIN_BASE_URL', default='control-panel')
