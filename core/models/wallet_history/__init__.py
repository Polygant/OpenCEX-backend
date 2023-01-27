from django.db import models
from django.utils.translation import gettext as _

from core.currency import CurrencyModelField
from exchange.models import BaseModel, UserMixinModel


class WalletHistoryItem(BaseModel, UserMixinModel):
    """
    Frontend "Wallet history" section data
    """
    # operation states
    STATE_PENDING = 0
    STATE_TO_BE_SENT = 1
    STATE_DONE = 2
    STATE_CANCELED = 3
    STATE_FAILED = 4
    STATE_UNKNOWN = 5
    STATE_WAIT_CONFIRMATION = 6
    STATE_REVERTED = 7
    STATE_VERIFYING = 8

    STATES = (
        (STATE_PENDING, _('Pending')),
        (STATE_TO_BE_SENT, _('To be sent')),
        (STATE_DONE, _('Done')),
        (STATE_CANCELED, _('Canceled')),
        (STATE_FAILED, _('Failed')),
        (STATE_UNKNOWN, _('Unknown')),
        (STATE_REVERTED, _('Reverted')),
        (STATE_VERIFYING, _('Verifying')),
    )

    # operation types
    OPERATION_TYPE_DEPOSIT = 1
    OPERATION_TYPE_WITHDRAWAL = 2
    OPERATION_TYPE_MERCHANT = 3
    OPERATION_TYPE_REVERT = 4
    OPERATION_TYPE_REVERT_RETURN = 5
    OPERATION_TYPE_REVERT_CHARGE = 6
    OPERATION_TYPE_STAKE = 7
    OPERATION_TYPE_UNSTAKE = 8
    OPERATION_TYPE_LOCK = 9
    OPERATION_TYPE_UNLOCK = 10
    OPERATION_TYPE_STAKE_EARNINGS = 11

    OPERATION_TYPES = (
        (OPERATION_TYPE_DEPOSIT, _('Deposit')),
        (OPERATION_TYPE_WITHDRAWAL, _('Withdrawal')),
        (OPERATION_TYPE_MERCHANT, _('Merchant')),
        (OPERATION_TYPE_REVERT, _('Revert')),
        (OPERATION_TYPE_REVERT_RETURN, _('Revert Return')),
        (OPERATION_TYPE_REVERT_CHARGE, _('Revert Charge')),
        (OPERATION_TYPE_STAKE, _('Stake')),
        (OPERATION_TYPE_UNSTAKE, _('Unstake')),
        (OPERATION_TYPE_LOCK, _('Lock')),
        (OPERATION_TYPE_UNLOCK, _('Unlock')),
        (OPERATION_TYPE_STAKE_EARNINGS, _('Stake Earnings')),
    )

    # paygate methods
    PAYGATE_METHOD_VISA = 0
    PAYGATE_METHOD_MASTERCARD = 1
    PAYGATE_METHOD_QIWI = 2
    PAYGATE_METHOD_ACCOUNT = 3
    PAYGATE_METHOD_REF_BONUS = 4

    PAYGATE_METHODS = (
        (PAYGATE_METHOD_VISA, 'Visa'),
        (PAYGATE_METHOD_MASTERCARD, 'Mastercard'),
        (PAYGATE_METHOD_QIWI, 'QIWI'),
        (PAYGATE_METHOD_ACCOUNT, 'Account'),
        (PAYGATE_METHOD_REF_BONUS, 'Referral bonus'),
    )

    transaction = models.OneToOneField('core.Transaction', on_delete=models.CASCADE, null=True)
    state = models.PositiveSmallIntegerField(choices=STATES, default=STATE_PENDING)
    operation_type = models.PositiveSmallIntegerField(choices=OPERATION_TYPES)
    currency = CurrencyModelField()
    amount = models.DecimalField(max_digits=32, decimal_places=8, default=0)
    # transaction hash for crypto and request id for fiat
    tx_hash = models.CharField(max_length=255, default=str)
    # wallet address for crypto and target account for fiat
    address = models.CharField(max_length=255, default=str)
    confirmations_count = models.PositiveSmallIntegerField(default=0)
    confirmed = models.BooleanField(default=False)
    paygate_id = models.PositiveSmallIntegerField(default=0)
    paygate_method = models.PositiveSmallIntegerField(choices=PAYGATE_METHODS, blank=True, null=True, default=None)

    class Meta:
        ordering = (
            '-created',
        )
        # in case of sorting and filtering
        indexes = [
            models.Index(fields=['created', 'updated']),
            models.Index(fields=['state']),
            models.Index(fields=['operation_type']),
            models.Index(fields=['currency']),
            models.Index(fields=['confirmed']),
            models.Index(fields=['paygate_id']),
            models.Index(fields=['paygate_method']),
        ]
