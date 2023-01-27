import logging

from celery.app import shared_task

from cryptocoins.scoring.manager import ScoreManager
from cryptocoins.utils.service import get_service_instance
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


@shared_task
def process_deffered_deposit(tx_id, address, amount, currency_code):
    amount = to_decimal(amount)
    is_scoring_ok = ScoreManager.is_address_scoring_ok(tx_id, address, amount, currency_code)
    service = get_service_instance()
    service.process_deposit(tx_id, address, amount, is_scoring_ok)
