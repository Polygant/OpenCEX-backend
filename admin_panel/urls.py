from django.conf import settings
from django.contrib import admin
from django.urls import include
from django.urls.conf import path

from admin_panel.views import admin_withdrawal_request_approve, admin_eth_withdrawal_request_approve, make_topup
from exchange.settings import ADMIN_BASE_URL

admin.autodiscover()

urls = [
    path(
       f'withdrawal_request/approve/btc/',
       admin_withdrawal_request_approve,
       name='admin_withdrawal_request_approve_btc'
    ),
    path(
       f'withdrawal_request/approve/eth/',
       admin_eth_withdrawal_request_approve,
       name='admin_withdrawal_request_approve_eth'
    ),
    path(
       f'make/top-up/',
       make_topup,
       name='admin_make_topup'
    ),
    path('', admin.site.urls),
]

urlpatterns = [
    path('admin_tools/', include('admin_tools.urls')),
    path(fr'{ADMIN_BASE_URL}/', include(urls)),
]
