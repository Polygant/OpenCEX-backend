import logging

from django.core.management.base import BaseCommand
from core.models import UserRestrictions
from core.models import Order

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Disables order creation for users and cancel opened orders'

    def add_arguments(self, parser):
        parser.add_argument('-e', '--exclude', help="list of excluded emails separated by comma", type=str)

    def handle(self, *args, **options):
        exclude = options.get('exclude')
        if exclude:
            exclude = exclude.split(',')

        restrictions_qs = UserRestrictions.objects.all()
        if exclude:
            restrictions_qs = restrictions_qs.exclude(
                user__email__in=exclude
            )
        restrictions_qs.update(disable_orders=True)

        orders_qs = Order.objects.filter(
            state=Order.STATE_OPENED
        )
        if exclude:
            orders_qs = orders_qs.exclude(
                user__email__in=exclude,
            )

        for order in orders_qs:
            order.delete(by_admin=True)
