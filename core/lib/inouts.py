import re
import urllib
from functools import partialmethod

from django.conf import settings
from django.db.transaction import atomic
from django.urls.base import reverse

from lib.helpers import to_decimal
from lib.utils import get_api_domain
from lib.utils import get_domain

PENDING = 0
COMPLETED = 1
FAILED = 2


class BasePayGate(object):
    """Base class for fiat inouts (sci) integration"""
    ID = 0
    NAME = 'base'
    SCI_URL = None
    ALLOW_CURRENCY = []

    @classmethod
    def parse_topup_id(cls, data):
        return int(re.search('([0-9]+$)', str(data)).group())

    @classmethod
    def cb_url(self, *args, **kwargs):
        return'https://{}{}'.format(get_api_domain(), reverse('sci_callback', kwargs={'gate_name': self.NAME.lower()}))

    @classmethod
    def _mk_url(self, method, obj):
        return 'https://{}{}'.format(get_domain(), '/account/{}/{}/{}'.format(self.NAME, method, obj.id))

    success_url = partialmethod(_mk_url, 'success')
    fail_url = partialmethod(_mk_url, 'fail')
    pending_url = partialmethod(_mk_url, 'pending')

    @classmethod
    def topup_url(self, obj):
        return '{}?{}'.format(self.SCI_URL, urllib.parse.urlencode(self.topup_params(obj)))

    @classmethod
    def __str__(self, *args, **kwargs):
        return self.NAME

    @classmethod
    def topup_id(cls, obj):
        return "{}_{}".format(get_domain(), str(obj.id)).replace('.', '')

    @classmethod
    def topup_fee(cls):
        return to_decimal(settings.SCI_TOPUP_FEE.get(cls.NAME, 0))

    @classmethod
    def do_topup_update(cls, instance, state, data):
        from core.models.inouts.transaction import Transaction
        state = state or PENDING

        with atomic():
            if state == COMPLETED and instance.state != COMPLETED and instance.tx is None:
                fee_rate = cls.topup_fee()
                instance.our_fee_amount = instance.amount * fee_rate
                final_amount = instance.amount - instance.our_fee_amount

                instance.tx = Transaction.topup(
                    user_id=instance.user_id,
                    currency=instance.currency,
                    amount=final_amount,
                )

            instance.state = state
            instance.data = data
            instance.save()

    @classmethod
    def make_withdrawal(cls, obj, action='process', *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def topup_params(cls, obj):
        raise NotImplementedError
