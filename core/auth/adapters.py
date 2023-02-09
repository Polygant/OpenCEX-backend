from allauth.account.adapter import DefaultAccountAdapter
from allauth.utils import email_address_exists
from django.contrib.sites.shortcuts import get_current_site
from rest_framework.exceptions import ValidationError


class AccountAdapter(DefaultAccountAdapter):

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
