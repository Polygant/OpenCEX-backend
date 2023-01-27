from django.db import models

from core.currency import CurrencyModelField


class AccumulationDetails(models.Model):
    """Keep accumulation details. Used in monitoring."""

    STATE_PENDING = 1
    STATE_COMPLETED = 2
    STATE_FAILED = 3

    STATES = (
        (STATE_PENDING, 'Pending'),
        (STATE_COMPLETED, 'Completed'),
        (STATE_FAILED, 'Failed'),
    )

    created = models.DateTimeField(auto_now_add=True)
    currency = CurrencyModelField()
    token_currency = CurrencyModelField(null=True)
    txid = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    from_address = models.CharField(max_length=100, db_index=True)
    to_address = models.CharField(max_length=100, default='')
    is_checked = models.BooleanField(default=False)
    state = models.PositiveSmallIntegerField(choices=STATES, default=STATE_PENDING)

    def complete(self):
        self.state = self.STATE_COMPLETED
        super(AccumulationDetails, self).save()

    def fail(self):
        self.state = self.STATE_FAILED
        super(AccumulationDetails, self).save()

    def __str__(self):
        return f'Accumulation {self.currency} TX {self.txid} from {self.from_address} -> {self.to_address}'
