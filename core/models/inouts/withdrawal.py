import datetime

from django.conf import settings
from django.db.models import JSONField
from django.db import models
from django.db.models import Sum, QuerySet
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from core.currency import CurrencyModelField
from core.exceptions.inouts import BadAmount
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.transaction import REASON_WITHDRAWAL
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.transaction import TRANSACTION_PENDING
from core.models.inouts.transaction import Transaction
from exchange.models import BaseModel
from exchange.models import UserMixinModel
from lib.exceptions import BaseError
from lib.fields import MoneyField

CREATED = 0
PENDING = 1
COMPLETED = 2
FAILED = 3
CANCELLED = 4
VERIFYING = 5


STATES = {CREATED: 'Created',
          PENDING: 'Pending',
          COMPLETED: 'Completed',
          FAILED: 'Failed',
          CANCELLED: 'Cancelled',
          VERIFYING: 'Verifying'
          }


class PayoutsFreezed(BaseError):
    default_detail = 'Payouts freezed'
    default_code = 'payouts_freezed'


class WithdrawalRequest(UserMixinModel, BaseModel):

    STATE_CREATED = CREATED
    STATE_PENDING = PENDING
    STATE_COMPLETED = COMPLETED
    STATE_FAILED = FAILED
    STATE_CANCELLED = CANCELLED
    STATE_VERIFYING = VERIFYING

    STATES = (
        (STATE_CREATED, _('Created')),
        (STATE_PENDING, _('Pending')),
        (STATE_COMPLETED, _('Completed')),
        (STATE_FAILED, _('Failed')),
        (STATE_CANCELLED, _('Cancelled')),
        (STATE_VERIFYING, _('Verifying')),
    )

    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    amount_usdt = MoneyField(default=0)
    state = models.IntegerField(choices=STATES, default=CREATED, null=False, blank=False)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name='withdrawal_request')

    txid = models.CharField(max_length=250, null=True, blank=True)

    approved = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)

    our_fee_amount = MoneyField(default=0)
    sci_gate_id = models.IntegerField(null=True, blank=True)

    data = JSONField(default=dict, blank=True)
    # SHA-256 hash
    confirmation_token = models.CharField(
        max_length=64, null=True, blank=True, unique=True, default=None)

    def change_state(self, target_state):
        n = self.__class__.objects.filter(id=self.id, state=self.state).update(state=target_state)
        if n != 1:
            raise ValidationError({
                'message': 'Bad state!',
                'type': 'state_incorrect'
            })

    def save(self, *args, **kwargs):
        if self.user.profile.is_payouts_freezed():
            raise PayoutsFreezed()

        min_amount = FeesAndLimits.get_limit(
            self.currency.code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.MIN_VALUE)
        max_amount = FeesAndLimits.get_limit(
            self.currency.code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.MAX_VALUE)

        blockchain_currency = self.data.get('blockchain_currency', None)
        withdrawal_fee = FeesAndLimits.get_fee(
            self.currency.code, FeesAndLimits.WITHDRAWAL, FeesAndLimits.ADDRESS, blockchain_currency)

        if self.amount < min_amount:
            raise BadAmount('minimal is {} but amount is {}'.format(min_amount, self.amount))
        if max_amount and self.amount > max_amount:
            raise BadAmount('limit is {} but amount is {}'.format(max_amount, self.amount))

        from core.cache import external_exchanges_pairs_price_cache
        price = external_exchanges_pairs_price_cache.get(
            '{}-{}'.format(self.currency.code, 'USDT'), 1)
        self.amount_usdt = self.amount * price

        # user_balance = BalanceManager.get_amount(self.user_id, self.currency)
        # if withdrawal_fee >= user_balance and not self.confirmed:
        #     raise BadAmount('fee is {} but balance is {}'.format(withdrawal_fee, user_balance))

        if self.approved and not self.confirmed:
            raise ValidationError({
                'message': 'can not approve unconfirmed request!',
                'type': 'withdrawal_unconfirmed'
            })

        with atomic():
            if not self.id:
                amount = - self.amount
                t = Transaction(reason=REASON_WITHDRAWAL,
                                user_id=self.user_id,
                                currency=self.currency,
                                amount=amount,
                                data={'withdrawal_data': self.data},
                                state=TRANSACTION_PENDING
                                )
                t.save()
                self.transaction = t
            return super(WithdrawalRequest, self).save(*args, **kwargs)

    def complete(self):
        # TODO: better check for race conditions!
        assert self.state in (CREATED, PENDING)
        assert self.transaction.state == TRANSACTION_PENDING
        with atomic():
            # self.change_state(COMPLETED)
            self.transaction.state = TRANSACTION_COMPLETED
            self.transaction.save()
            self.state = COMPLETED
            super(WithdrawalRequest, self).save()

    def cancel(self):
        # TODO: better check for race conditions!
        assert self.state == CREATED
        assert self.transaction.state == TRANSACTION_PENDING
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        with atomic():
            self.change_state(CANCELLED)
            self.transaction.cancel()
            self.state = CANCELLED
            super(WithdrawalRequest, self).save()
            create_or_update_wallet_history_item_from_transaction(self.transaction)

    def fail(self):
        # TODO: better check for race conditions!
        assert self.state in (CREATED, PENDING)
        assert self.transaction.state == TRANSACTION_PENDING
        from core.tasks.inouts import withdrawal_failed_email
        with atomic():
            self.change_state(FAILED)
            self.state = FAILED
            self.transaction.cancel()
            super(WithdrawalRequest, self).save()
            withdrawal_failed_email.apply_async([self.id])

    def complete_to_fail(self):
        if self.state != self.STATE_COMPLETED:
            raise
        self.transaction.state = TRANSACTION_PENDING
        self.state = self.STATE_PENDING
        self.fail()

    def pause(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        if self.state == self.STATE_CREATED and self.confirmed:
            self.state = self.STATE_VERIFYING
            super(WithdrawalRequest, self).save()
            create_or_update_wallet_history_item_from_transaction(self.transaction)

    def unpause(self):
        from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
        if self.state == self.STATE_VERIFYING:
            self.state = self.STATE_CREATED
            super(WithdrawalRequest, self).save()
            create_or_update_wallet_history_item_from_transaction(self.transaction)

    @classmethod
    def sci_to_process(cls):
        dt = datetime.datetime.now() - datetime.timedelta(seconds=settings.SCI_WITHDRAWAL_CHECK_TIMEOUT)
        return cls.objects.exclude(sci_gate_id__isnull=True).filter(state__in=[CREATED, PENDING], created__gte=dt, approved=True, confirmed=True)

    @classmethod
    def crypto_to_process(cls, currency) -> QuerySet:
        return cls.objects.filter(
            currency=currency,
            state=CREATED,
            approved=True,
            confirmed=True
        )

    def __str__(self):
        return f'Withdrawal request #{self.id} ({self.get_state_display()})'

    class Meta:
        indexes = [
            # there would be frequent queries by token
            models.Index(fields=['confirmation_token']),
        ]


class WithdrawalLimitLevel(models.Model):
    # id
    amount = MoneyField(default=0)
    level = models.IntegerField()

    @classmethod
    def get_by_level(cls, level):
        assert type(level) == int
        limit_level: cls = cls.objects.filter(level=0).first()
        if not limit_level:
            limit_level: cls = cls.objects.create(
                level=level,
                amount=100
            )
        return limit_level

    class Meta:
        indexes = [
            # there would be frequent queries by token
            models.Index(fields=['level']),
        ]


class WithdrawalUserLimit(UserMixinModel, BaseModel):
    # id
    # user
    limit = models.ForeignKey(null=True, blank=True, default=None,
                              to=WithdrawalLimitLevel, on_delete=models.CASCADE)

    @classmethod
    def get_limits(cls, user):
        user_limit: WithdrawalUserLimit = cls.objects.filter(user=user).first()
        if not user_limit:
            limit_level: WithdrawalLimitLevel = WithdrawalLimitLevel.get_by_level(level=0)
            user_limit: WithdrawalUserLimit = cls.objects.create(user=user, limit=limit_level)

        limit_level = user_limit.limit
        today_date = datetime.date.today()
        current_limit_amount = WithdrawalRequest.objects.filter(
            user=user,
            state__in=[CREATED, PENDING, COMPLETED, VERIFYING],
            created__gte=today_date.replace(day=1)
        ).aggregate(
            sum=Sum('amount_usdt')
        )['sum'] or 0

        return {
            'limit': limit_level,
            'amount': current_limit_amount
        }
