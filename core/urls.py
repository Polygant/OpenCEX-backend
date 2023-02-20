from django.conf.urls import url
from django.views.generic.base import View
from core.views import facade


class NullView(View):
    pass


urlpatterns = [
    url(r'email_confirm/(?P<key>[-:\w]+)/$', NullView.as_view(),
        name='account_confirm_email'),
    url(r'^account-email-verification-sent/', NullView.as_view(), name='account_email_verification_sent'),
    url(r'^account/reset-password/(?P<uidb64>[-:\w]+)/(?P<token>[-:\w]+)', NullView.as_view(), name='password_reset_confirm'),
    url(r'^robots.txt', facade.robots, name='robots'),
    url(r'^sitemap.xml', facade.sitemap, name='sitemap'),
]