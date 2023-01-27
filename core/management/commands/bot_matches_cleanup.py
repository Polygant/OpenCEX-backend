import logging

from django.core.management.base import BaseCommand

from core.utils.cleanup_utils import get_orders_to_delete_ids, strip_orders

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup bots orders and match data'

    def handle(self, *args, **options):
        log.info('Get ids')
        order_ids = get_orders_to_delete_ids()
        log.info('Start cleanup')
        strip_orders(order_ids)
        log.info('Done')

