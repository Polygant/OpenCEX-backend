from allauth.account.adapter import DefaultAccountAdapter
from allauth.utils import email_address_exists
from django.utils import translation
from rest_framework.exceptions import ValidationError

from core.utils import get_rand_code


class AccountAdapter(DefaultAccountAdapter):

    def validate_unique_email(self, email):
        if email_address_exists(email):
            raise ValidationError({
                'type': 'wrong_data'
            })
        return email

    def __get_lang(self):
        if hasattr(self.request, "data") and "lang" in self.request.data:
            return self.request.data["lang"]
        elif hasattr(self.request, "lang"):
            return self.request.lang
        else:
            return "en"

    def render_mail(self, template_prefix, email, context, headers=None):
        lang = self.__get_lang()
        context.update({"lang": lang})
        with translation.override(lang):
            return super().render_mail(template_prefix, email, context, headers)

    def generate_emailconfirmation_key(self, email):
        return get_rand_code(6)
