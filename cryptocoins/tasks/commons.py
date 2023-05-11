import base64
import logging

from celery import shared_task
from django.conf import settings

from core.consts.currencies import CRYPTO_COINS_PARAMS
from core.models import DisabledCoin
from cryptocoins.models import LastProcessedBlock
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.monitoring.monitoring_processor import MonitoringProcessor
from lib.notifications import send_telegram_message

log = logging.getLogger(__name__)


@shared_task
def mark_accumulated_topups():
    for currency in MonitoringProcessor.monitors:
        mark_accumulated_topups_for_currency.apply_async([currency])


@shared_task
def mark_accumulated_topups_for_currency(currency):
    MonitoringProcessor.process(currency)


@shared_task
def check_crypto_workers():
    """Checks cryptoworkers state using last processed block"""
    for last_processed_block in LastProcessedBlock.objects.all():
        currency = last_processed_block.currency

        if DisabledCoin.is_coin_disabled(currency):
            continue

        coin_params = CRYPTO_COINS_PARAMS[currency]

        if coin_params.latest_block_fn:
            error_msg = ''
            fn = coin_params.latest_block_fn
            try:
                block_id = fn(currency)
            except Exception as e:
                error_msg = str(e)
                block_id = None

            if not block_id:
                msg = f'Can\'t fetch {currency.code} latest block on {settings.INSTANCE_NAME}\n{error_msg}'
                send_telegram_message(msg, chat_id=settings.TELEGRAM_ALERTS_CHAT_ID)
                continue

            crypto_diff = coin_params.blocks_monitoring_diff
            if not crypto_diff:
                continue

            diff = int(block_id) - last_processed_block.block_id
            if diff > crypto_diff:
                msg = f'{currency.code} - {settings.INSTANCE_NAME} worker does not work\nLatest checked block:{last_processed_block.block_id}'
                send_telegram_message(msg, chat_id=settings.TELEGRAM_ALERTS_CHAT_ID)
