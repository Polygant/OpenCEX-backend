from django.db.models import JSONField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class DepositsWithdrawalsStats(models.Model):
    created = models.DateTimeField(default=timezone.now)
    stats = JSONField(default=dict, encoder=DjangoJSONEncoder)
