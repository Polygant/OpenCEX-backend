from cryptos import Bitcoin
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from core.consts.currencies import CURRENCIES_LIST
from core.currency import Currency
from core.pairs import PAIRS_LIST
from cryptocoins.tasks.eth import ethereum_manager
from cryptocoins.tasks.trx import tron_manager
from cryptocoins.tasks.bnb import bnb_manager
from lib.cipher import AESCoderDecoder

CryptoBitcoin = Bitcoin()
User = get_user_model()


class BaseApproveAdminForm(forms.Form):
    key = forms.CharField(label='Password', max_length=255, widget=forms.PasswordInput())

    def get_encrypted_string(self):
        raise NotImplementedError

    def clean_key(self):
        key = self.cleaned_data['key']
        if not key:
            raise ValidationError("Bad password!!")

        try:
            to_check_string = self.get_encrypted_string()
            res = AESCoderDecoder(key).decrypt(to_check_string)
            if not res:
                raise ValidationError("Bad private key")
        except Exception as e:
            raise ValidationError("Bad password!")

        return key


class BtcApproveAdminForm(forms.Form):
    # TODO validate key
    key = forms.CharField(label='Private Key', max_length=255, widget=forms.PasswordInput())

    def clean_key(self):
        key = self.cleaned_data['key']
        if len(key) != 52:
            raise ValidationError("Bad format private key!")

        if key[0] not in ['K', 'L']:
            raise ValidationError("Bad format private key.")

        try:
            CryptoBitcoin.privtopub(key)
        except AssertionError as e:
            raise ValidationError("Bad format private key")

        return key


class EthApproveAdminForm(BaseApproveAdminForm):

    def get_encrypted_string(self):
        return ethereum_manager.get_keeper_wallet().private_key


class MakeTopUpForm(forms.Form):
    password = forms.CharField(label='Password', max_length=255, widget=forms.PasswordInput())
    currency = forms.ChoiceField(label='Currency', choices=CURRENCIES_LIST, )
    amount = forms.DecimalField(label='Amount')
    user = forms.CharField(label='User email', max_length=255, )

    def clean_password(self):
        key = self.cleaned_data['password']
        if not key or key != settings.ADMIN_MASTERPASS:
            raise ValidationError("Bad password!")
        return key

    def clean_currency(self):
        currency = self.cleaned_data['currency']
        return Currency.get(currency)

    def clean_user(self):
        user_email = self.cleaned_data['user']
        user = User.objects.filter(username__iexact=user_email).first()
        if not user:
            raise ValidationError("Bad user!")
        return user


class PairAdminForm(forms.ModelForm):
    pair = forms.ChoiceField(choices=[(p[1], p[1]) for p in PAIRS_LIST])


class TrxApproveAdminForm(BaseApproveAdminForm):

    def get_encrypted_string(self):
        return tron_manager.get_keeper_wallet().private_key


class BnbApproveAdminForm(BaseApproveAdminForm):

    def get_encrypted_string(self):
        return bnb_manager.get_keeper_wallet().private_key
