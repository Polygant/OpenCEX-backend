import logging

from django.db import models
from django.db.models import Count, Case, When, Q, IntegerField
from django.db.transaction import atomic
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ValidationError

from core.consts.currencies import CRYPTO_ADDRESS_VALIDATORS
from core.currency import CurrencyModelField
from core.exceptions.inouts import NotEnoughFunds
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import REASON_WALLET_REVERT_CHARGE
from core.models.inouts.transaction import REASON_WALLET_REVERT_RETURN
from core.models.inouts.transaction import Transaction
from cryptocoins.exceptions import ScoringClientError
from cryptocoins.scoring.manager import ScoreManager
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.helpers import copy_instance

logger = logging.getLogger('wallet')


class WalletTransactions(BaseModel):
    STATUS_NOT_SET = 0
    STATUS_REVERTED = 99

    STATUS_LIST = (
        (STATUS_NOT_SET, _('Not set')),
        (STATUS_REVERTED, _('Reverted')),
    )

    MONITORING_STATE_NOT_CHECKED = 1
    MONITORING_STATE_ACCUMULATED = 2
    MONITORING_STATE_NOT_ACCUMULATED = 3
    MONITORING_STATE_WRONG_AMOUNT = 4
    MONITORING_STATE_WRONG_ACCUMULATION = 5

    MONITORING_STATES = (
        (MONITORING_STATE_NOT_CHECKED, _('Not checked')),
        (MONITORING_STATE_ACCUMULATED, _('Accumulated')),
        (MONITORING_STATE_NOT_ACCUMULATED, _('Not accumulated')),
        (MONITORING_STATE_WRONG_AMOUNT, _('Wrong amount')),
        (MONITORING_STATE_WRONG_ACCUMULATION, _('Wrong accumulation')),
    )

    STATE_CREATED = 1
    STATE_VERIFICATION_FAILED = 2
    STATE_WAITING_FOR_KYT_APPROVE = 3
    STATE_KYT_APPROVE_ON_CHECK = 4
    STATE_KYT_APPROVE_PLATFORM_ERROR = 5
    STATE_KYT_APPROVE_REJECTED = 6
    STATE_WAITING_FOR_ACCUMULATION = 7
    STATE_GAS_REQUIRED = 8
    STATE_WAITING_FOR_GAS = 9
    STATE_READY_FOR_ACCUMULATION = 10
    STATE_ACCUMULATION_IN_PROGRESS = 11
    STATE_ACCUMULATED = 12
    STATE_BALANCE_TOO_LOW = 13
    STATE_MANUAL_DEPOSIT = 14
    STATE_OLD_WALLET_DEPOSIT = 15
    STATE_EXTERNAL_ACCUMULATED = 16
    STATE_GAS_PRICE_TOO_HIGH = 17

    STATES = (
        (STATE_CREATED, 'Created'),
        (STATE_VERIFICATION_FAILED, 'Verification failed'),
        (STATE_WAITING_FOR_KYT_APPROVE, 'Waiting for KYT approve'),
        (STATE_KYT_APPROVE_ON_CHECK, 'KYT approve on check'),
        (STATE_KYT_APPROVE_PLATFORM_ERROR, 'KYT approve platform error'),
        (STATE_KYT_APPROVE_REJECTED, 'KYT approve rejected'),
        (STATE_WAITING_FOR_ACCUMULATION, 'Waiting for accumulation'),
        (STATE_GAS_REQUIRED, 'Gas Required'),
        (STATE_WAITING_FOR_GAS, 'Waiting for gas'),
        (STATE_READY_FOR_ACCUMULATION, 'Ready for accumulation'),
        (STATE_ACCUMULATION_IN_PROGRESS, 'Accumulation in progress'),
        (STATE_ACCUMULATED, 'Accumulated'),
        (STATE_BALANCE_TOO_LOW, 'Balance too low'),
        (STATE_MANUAL_DEPOSIT, 'Manual deposit'),
        (STATE_OLD_WALLET_DEPOSIT, 'Old wallet deposit'),
        (STATE_EXTERNAL_ACCUMULATED, 'External accumulated'),
        (STATE_GAS_PRICE_TOO_HIGH, 'Gas price too high'),
    )

    ACCUMULATION_READY_STATES = [
        STATE_WAITING_FOR_ACCUMULATION,
        STATE_GAS_REQUIRED,
        STATE_WAITING_FOR_GAS,
        STATE_READY_FOR_ACCUMULATION,
        STATE_GAS_PRICE_TOO_HIGH,
    ]

    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    fee_amount = MoneyField(default=0)
    wallet = models.ForeignKey('core.UserWallet', on_delete=models.CASCADE, related_name='wallet_transaction')
    tx_hash = models.CharField(max_length=250)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='wallet_transaction', null=True)
    status = models.PositiveSmallIntegerField(default=STATUS_NOT_SET, choices=STATUS_LIST)
    monitoring_state = models.PositiveSmallIntegerField(default=MONITORING_STATE_NOT_CHECKED, choices=MONITORING_STATES)
    state = models.PositiveSmallIntegerField(choices=STATES, default=STATE_CREATED)
    external_accumulation_address = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['state']),
        ]

    def save(self, *args, **kwargs):
        assert self.amount > 0
        is_insert = self._state.adding is True
        super(WalletTransactions, self).save(*args, **kwargs)
        if is_insert:
            self.__check_deposit()

    def __check_deposit(self):
        deposit_min_limit = FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT,
                                                    FeesAndLimits.MIN_VALUE)
        deposit_max_limit = FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT,
                                                    FeesAndLimits.MAX_VALUE)

        with atomic():
            if (not self.wallet.user.restrictions.disable_topups
                    and not self.wallet.is_deposits_blocked
                    and not deposit_min_limit > self.amount
                    and not self.amount > deposit_max_limit
            ):
                self.state = self.STATE_WAITING_FOR_KYT_APPROVE

                self.fee_amount = self.get_fee_amount()
                tx_amount = self.amount - self.fee_amount
                assert tx_amount > 0

                from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction

                self.transaction = Transaction.pending(
                    user_id=self.wallet.user_id,
                    currency=self.currency,
                    amount=tx_amount,
                    data={'txid': self.tx_hash},
                    reason=REASON_TOPUP,
                )
                create_or_update_wallet_history_item_from_transaction(self.transaction)
            else:
                self.state = self.STATE_VERIFICATION_FAILED

            super(WalletTransactions, self).save()

    def get_fee_amount(self):
        return FeesAndLimits.get_fee(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.ADDRESS)

    def set_external_accumulation_address(self, address: str):
        is_valid_fn = CRYPTO_ADDRESS_VALIDATORS[self.wallet.blockchain_currency]
        if not is_valid_fn(address):
            raise ValidationError('Incorrect address')
        if address.lower() == self.wallet.address:
            raise ValidationError('Incorrect address. Cannot transfer to yourself')

        self.state = self.STATE_WAITING_FOR_ACCUMULATION
        self.external_accumulation_address = address
        super(WalletTransactions, self).save()

    def check_scoring(self):
        if self.state not in [self.STATE_WAITING_FOR_KYT_APPROVE, self.STATE_KYT_APPROVE_PLATFORM_ERROR]:
            return
        if ScoreManager.need_to_check_score(self.tx_hash, self.wallet.address, self.amount, self.currency.code):
            try:
                token_currency = self.wallet.currency if self.wallet.blockchain_currency != self.wallet.currency else None
                is_scoring_ok = ScoreManager.is_address_scoring_ok(
                    self.tx_hash,
                    self.wallet.address,
                    self.amount,
                    self.wallet.blockchain_currency,
                    token_currency
                )
                if is_scoring_ok:
                    self.topup_tx()
                else:
                    self.state = self.STATE_KYT_APPROVE_REJECTED

            except ScoringClientError:
                self.state = self.STATE_KYT_APPROVE_PLATFORM_ERROR

        else:
            self.state = self.STATE_WAITING_FOR_ACCUMULATION
            self.topup_tx()
        super(WalletTransactions, self).save()

    def topup_tx(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction

        if not self.transaction:
            # delete this later. Tx created at first save
            with atomic():
                self.state = self.STATE_WAITING_FOR_ACCUMULATION
                self.transaction = Transaction.topup(
                    user_id=self.wallet.user_id,
                    currency=self.currency,
                    amount=self.amount,
                    data={'txid': self.tx_hash},
                )
                self.save()
                create_or_update_wallet_history_item_from_transaction(self.transaction)
                return self
        else:
            if self.transaction.is_pending:
                self.transaction.save(update_balance_pending=True)
                create_or_update_wallet_history_item_from_transaction(self.transaction)
                return self


    def _revert(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        try:
            with atomic():
                new_transaction: Transaction = copy_instance(self.transaction, Transaction)
                new_transaction.revert(
                    return_status=REASON_WALLET_REVERT_RETURN,
                    charge_status=REASON_WALLET_REVERT_CHARGE,
                )
                new_transaction.save()
                paygeate_revert = WalletTransactionsRevert(
                    user_id=new_transaction.user_id,
                    transaction=new_transaction,
                    origin_transaction=self.transaction,
                    wallet_transaction=self
                )
                paygeate_revert.save()
                create_or_update_wallet_history_item_from_transaction(
                    new_transaction,
                    instance=self.transaction.wallethistoryitem
                )
                self.status = self.STATUS_REVERTED
                self.save()
        except NotEnoughFunds as e:
            raise ValidationError(f'Not enough funds! '
                                  f'user {new_transaction.user_id}, '
                                  f'{new_transaction.amount} '
                                  f'{new_transaction.currency}'
                                  )

    def force_deposit(self):
        self.topup_tx()
        self.wallet.unblock()

    def revert(self):
        if self.status == self.STATUS_REVERTED:
            raise ValidationError(f'the topup {self.id} has already been reverted!')

        self._revert()

    def set_ready_for_accumulation(self):
        if self.state == self.STATE_READY_FOR_ACCUMULATION:
            return
        self.state = self.STATE_READY_FOR_ACCUMULATION
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    def set_accumulated(self):
        if self.state in [self.STATE_ACCUMULATED, self.STATE_EXTERNAL_ACCUMULATED]:
            return
        self.state = self.STATE_EXTERNAL_ACCUMULATED if self.external_accumulation_address else self.STATE_ACCUMULATED
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    def set_gas_required(self):
        if self.state == self.STATE_GAS_REQUIRED:
            return
        self.state = self.STATE_GAS_REQUIRED
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    def set_waiting_for_gas(self):
        if self.state == self.STATE_WAITING_FOR_GAS:
            return
        self.state = self.STATE_WAITING_FOR_GAS
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    def set_accumulation_in_progress(self):
        if self.state == self.STATE_ACCUMULATION_IN_PROGRESS:
            return
        self.state = self.STATE_ACCUMULATION_IN_PROGRESS
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    def set_balance_too_low(self):
        if self.state == self.STATE_BALANCE_TOO_LOW:
            return
        self.state = self.STATE_BALANCE_TOO_LOW
        super(WalletTransactions, self).save(update_fields=['updated', 'state'])

    @classmethod
    def get_ready_for_accumulation(cls, blockchain_currency):
        from core.models import UserWallet

        wallet_transactions_qs = WalletTransactions.objects.annotate(
            not_ready_count=Count(
                Case(
                    When(
                        ~Q(wallet__wallet_transaction__state=WalletTransactions.STATE_VERIFICATION_FAILED)
                        & (
                                Q(wallet__wallet_transaction__state__lt=WalletTransactions.STATE_WAITING_FOR_ACCUMULATION)
                                | Q(wallet__wallet_transaction__state=WalletTransactions.STATE_ACCUMULATION_IN_PROGRESS)
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
        ).filter(
            wallet__blockchain_currency=blockchain_currency,
            state__in=WalletTransactions.ACCUMULATION_READY_STATES,
            not_ready_count=0,
        ).exclude(
            wallet__block_type=UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION,
        ).prefetch_related('wallet', 'wallet__wallet_transaction').order_by('created')

        to_accumulate_from_addresses = []  # uniq addresses
        to_accumulate = []

        for wallet_transaction in wallet_transactions_qs:
            if wallet_transaction.wallet.address in to_accumulate_from_addresses:
                continue
            to_accumulate_from_addresses.append(wallet_transaction.wallet.address)
            to_accumulate.append(wallet_transaction)
        return to_accumulate

    @classmethod
    def get_ready_for_external_accumulation(cls, blockchain_currency):
        return WalletTransactions.objects.filter(
            wallet__blockchain_currency=blockchain_currency,
            state__in=WalletTransactions.ACCUMULATION_READY_STATES,
            external_accumulation_address__isnull=False,
        )


class WalletTransactionsRevert(UserMixinModel, BaseModel):
    wallet_transaction = models.ForeignKey(
        WalletTransactions,
        on_delete=models.CASCADE,
        related_name='wallet_transactions_revert',
    )
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE,
                                    related_name='wallet_tr_reverted_transaction')
    origin_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='wallet_tr_origin_transaction',
        null=True,
        blank=True,
    )
