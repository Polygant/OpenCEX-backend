from django.db import models

from lib.fields import MoneyField


class AccumulationTransaction(models.Model):
    # tx which send gas to user wallet to make accumulation
    TX_TYPE_GAS_DEPOSIT = 1
    # tx which send user wallet amount to cold wallet
    TX_TYPE_ACCUMULATION = 2

    TX_TYPES = [
        (TX_TYPE_GAS_DEPOSIT, 'Gas deposit'),
        (TX_TYPE_ACCUMULATION, 'Accumulation'),
    ]

    STATE_PENDING = 1
    STATE_COMPLETED = 2
    STATE_FAILED = 3

    STATES = [
        (STATE_PENDING, 'Pending'),
        (STATE_COMPLETED, 'Completed'),
        (STATE_FAILED, 'Failed'),
    ]

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    wallet_transaction = models.ForeignKey('core.WalletTransactions', on_delete=models.DO_NOTHING, null=True)
    amount = MoneyField(decimal_places=18, default=0)
    tx_type = models.PositiveSmallIntegerField(choices=TX_TYPES)
    tx_state = models.PositiveSmallIntegerField(choices=STATES, default=STATE_PENDING)
    tx_hash = models.TextField(default='', unique=True)

    class Meta:
        ordering = [
            '-updated',
        ]
        indexes = [
            models.Index(fields=['tx_hash', 'tx_type', 'tx_state']),
        ]

    def complete(self, is_gas=False):
        self.tx_state = AccumulationTransaction.STATE_COMPLETED
        self.save(update_fields=['tx_state', 'updated'])
        if is_gas:
            self.wallet_transaction.set_ready_for_accumulation()
        else:
            self.wallet_transaction.set_accumulated()
