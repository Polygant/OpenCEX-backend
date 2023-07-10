from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.urls.conf import include
from django_otp.admin import OTPAdminSite

from exchange.settings import ADMIN_BASE_URL

if settings.ENABLE_OTP_ADMIN:
    admin.site.__class__ = OTPAdminSite

admin.autodiscover()
admin.site.enable_nav_sidebar = False

urlpatterns = [
    path('api/', include('exchange.api_urls')),
    path('apiadmin/', include('admin_rest.urls')),
    path('', include('core.urls')),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler404 = 'exchange.views.handler404'


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
