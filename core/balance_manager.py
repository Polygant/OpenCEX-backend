import logging

from django.db.models import F

from core.exceptions.inouts import NotEnoughFunds
from core.exceptions.inouts import NotEnoughHold
from core.models.inouts.balance import Balance
from core.signals.inouts import balance_changed
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class BalanceManager:

    @staticmethod
    def set_hold(user_id, currency, amount, amount_in_orders):
        """
        Decrease amount and increase amount_in_orders
        """
        amount = to_decimal(abs(amount))

        result = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
            amount__gte=amount
        ).update(
            amount=F('amount') - amount,
            amount_in_orders=amount_in_orders,
        )

        if result != 1:
            raise NotEnoughFunds()

        balance_changed.send(sender=BalanceManager, user_id=user_id)

    @staticmethod
    def free_hold(user_id, currency, amount, amount_in_orders):
        """
        Cancel order
        """
        amount = to_decimal(abs(amount))

        result = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
        ).update(
            amount=F('amount') + amount,
            amount_in_orders=amount_in_orders,
        )

        if result != 1:
            raise NotEnoughHold()

        balance_changed.send(sender=BalanceManager, user_id=user_id)

    @staticmethod
    def spend_hold(user_id, currency, amount):
        """
        Decrease hold amount
        """
        amount = to_decimal(abs(amount))

        result = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
        ).update(
            amount_in_orders=amount,
        )

        if result != 1:
            raise NotEnoughHold()

        balance_changed.send(sender=BalanceManager, user_id=user_id)

    @staticmethod
    def increase_amount(user_id, currency, amount):
        amount = abs(amount)

        qs = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
        )
        if qs.exists():
            qs.update(
                amount=F('amount') + amount,
            )
        else:
            # create balance
            Balance.objects.create(
                user_id=user_id,
                currency=currency,
                amount=amount,
            )
        balance_changed.send(sender=BalanceManager, user_id=user_id)

    @staticmethod
    def decrease_amount(user_id, currency, amount):
        amount = to_decimal(abs(amount))

        result = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
            amount__gte=amount,
        ).update(
            amount=F('amount') - amount,
        )

        if result != 1:
            raise NotEnoughFunds()

        balance_changed.send(sender=BalanceManager, user_id=user_id)

    @staticmethod
    def get_amount(user_id, currency):
        balance = Balance.objects.filter(
            user_id=user_id,
            currency=currency,
        ).only(
            'amount',
        ).first()

        if balance is not None:
            return balance.amount

        return to_decimal(0)
