import logging

from celery import shared_task

from cryptocoins.cold_wallet_stats import StatsProcessor
from cryptocoins.models.stats import DepositsWithdrawalsStats

log = logging.getLogger(__name__)


@shared_task
def calculate_topups_and_withdrawals(current_stats: DepositsWithdrawalsStats = None):
    StatsProcessor.process(current_stats)
