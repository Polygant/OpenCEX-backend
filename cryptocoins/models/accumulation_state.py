from django.db import models

from lib.fields import MoneyField


class AccumulationState(models.Model):
    """
    Accumulation state for both ETH and tokens
    """
    STATE_WAITING_FOR_CHECK = 1
    STATE_LOW_BALANCE = 2
    STATE_GAS_REQUIRED = 3
    STATE_WAITING_FOR_GAS = 4
    STATE_READY_FOR_ACCUMULATION = 5
    STATE_ACCUMULATION_IN_PROCESS = 6
    STATE_COMPLETED = 7
    STATE_ACCUMULATION_BLOCKED = 8

    STATES = (
        (STATE_WAITING_FOR_CHECK, 'Waiting for check'),
        (STATE_LOW_BALANCE, 'Low balance'),
        (STATE_GAS_REQUIRED, 'Gas required'),
        (STATE_WAITING_FOR_GAS, 'Waiting for gas'),
        (STATE_READY_FOR_ACCUMULATION, 'Ready'),
        (STATE_ACCUMULATION_IN_PROCESS, 'Accumulation in process'),
        (STATE_COMPLETED, 'Completed'),
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    wallet = models.OneToOneField('core.UserWallet', on_delete=models.DO_NOTHING)
    current_balance = MoneyField(decimal_places=18, default=0)
    state = models.PositiveSmallIntegerField(choices=STATES)

    def __str__(self):
        return f'{self.wallet} {self.current_balance} {self.get_state_display()}'

    class Meta:
        ordering = [
            '-updated',
        ]
        indexes = [
            models.Index(fields=['state']),
        ]