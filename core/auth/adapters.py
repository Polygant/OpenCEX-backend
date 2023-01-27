from allauth.account.adapter import DefaultAccountAdapter
from allauth.utils import email_address_exists
from django.contrib.sites.shortcuts import get_current_site
from rest_framework.exceptions import ValidationError


class AccountAdapter(DefaultAccountAdapter):

    _tmp = {}

    def set_tmp(self, key, val):
        self._tmp[key] = val
        return self._tmp

    def get_tmp(self, key, default=None):
        res = self._tmp.get(key, default)
        return res

    def clear_tmp(self, key=None):
        if key and key in self._tmp:
            del self._tmp[key]

        if key is None:
            self._tmp = {}

    def validate_unique_email(self, email):
        if email_address_exists(email):
            raise ValidationError({
                'type': 'wrong_data'
            })
        return email

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        current_site = get_current_site(request)

        activate_url = self.get_email_confirmation_url(
            request,
            emailconfirmation)
        ctx = {
            "user": emailconfirmation.email_address.user,
            "activate_url": activate_url,
            "current_site": current_site,
            "key": emailconfirmation.key,
            "lang": getattr(request, 'lang', None) or 'en'
        }
        if signup:
            email_template = 'account/email/email_confirmation_signup'
        else:
            email_template = 'account/email/email_confirmation'

        self.send_mail(email_template,
                       emailconfirmation.email_address.email,
                       ctx)
