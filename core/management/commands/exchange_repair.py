import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.consts.orders import ORDER_CANCELED
from core.models import Order, ExecutionResult, Transaction
from core.models.inouts.transaction import REASON_ORDER_CACHEBACK, TRANSACTION_COMPLETED
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cache back broken exchange orders'

    def handle(self, *args, **options):
        from django.db import transaction
        orders = Order.objects.filter(
            ~Q(state=ORDER_CANCELED) &
            Q(cost__gte=1)
        ).order_by(
            'created',
            'id',
        )

        log.info(f'count: %s' % (orders.count(), ))

        with transaction.atomic():
            for order in orders:
                transaction = Transaction(
                    user_id=order.user_id,
                    reason=REASON_ORDER_CACHEBACK,
                    state=TRANSACTION_COMPLETED,
                    currency=order.pair.quote,
                    amount=order.cost
                )
                log.info(f'order: %s' % (order.id,))
                transaction.save()
                matched: ExecutionResult = order.executionresult_set.filter(Q(cacheback_transaction=None) & Q(cancelled=False)).order_by('-id',).first()
                matched.cacheback_transaction = transaction
                matched.save()
                order.cost = to_decimal(0)
                order.save()
                log.info(f'[%s] match id: %s, amount: %.8f, curr: %s' % (order.id, matched.id, transaction.amount, transaction.currency, ))
        log.info('Done')

