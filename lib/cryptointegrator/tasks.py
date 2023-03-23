import logging
from typing import List

from celery.app import shared_task

from cryptocoins.exceptions import CoinServiceError
from cryptocoins.utils.service import get_service_instance

log = logging.getLogger(__name__)


@shared_task
def process_new_blocks():
    get_service_instance().process_new_blocks()


@shared_task
def create_wallet(user_id, is_new=False):
    service = get_service_instance()

    if service is not None:
        try:
            wallet = service.create_userwallet(user_id, is_new=is_new)
            return wallet.id
        except CoinServiceError as e:
            pass


@shared_task
def get_keeper_balance():
    data = {'currency': None, 'addr': None, 'balance': None}

    service = get_service_instance()
    if service is not None:
        try:
            keeper_wallet = service.get_keeper_wallet()
            keeper_balance = service.get_keeper_balance()

            return {
                'currency': service.currency.code,
                'addr': keeper_wallet.address,
                'balance': keeper_balance,
            }
        except CoinServiceError as e:
            pass
    return data


@shared_task
def payouts(*args, **kwargs):
    service = get_service_instance()

    if service is not None:
        try:
            service.process_withdrawals()
        except CoinServiceError as e:
            pass


@shared_task
def accumulate():
    service = get_service_instance()

    if service is not None:
        try:
            service.accumulate()
        except CoinServiceError as e:
            pass


@shared_task
def check_for_scoring():
    service = get_service_instance()

    if service is not None:
        try:
            service.check_for_scoring()
        except CoinServiceError as e:
            pass


def generate_crypto_schedule(conf: List[dict]) -> dict:
    schedule = {}

    for item in conf:
        currency_symbol = item.get('currency').lower()

        if not item.get('enabled'):
            log.info('Skipping generating schedule for %s', currency_symbol)
            continue

        else:
            log.info('Generating schedule for %s', currency_symbol)

        if item.get('accumulate_period') is not False:
            schedule[f'accumulate {currency_symbol}'] = {
                'task': 'lib.cryptointegrator.tasks.accumulate',
                'schedule': item.get('accumulate_period'),
                'args': (),
                'options': {
                    'expires': 10,
                    'queue': currency_symbol,
                }
            }

        if item.get('payouts_period') is not False:
            schedule[f'payouts {currency_symbol}'] = {
                'task': 'lib.cryptointegrator.tasks.payouts',
                'schedule': item.get('payouts_period'),
                'args': (),
                'options': {
                    'expires': 10,
                    'queue': currency_symbol,
                }
            }

        if item.get('process_new_blocks_period') is not False:
            schedule[f'process new blocks {currency_symbol}'] = {
                'task': 'lib.cryptointegrator.tasks.process_new_blocks',
                'schedule': item.get('process_new_blocks_period'),
                'args': (),
                'options': {
                    'expires': 10,
                    'queue': currency_symbol,
                }
            }
        schedule[f'check for scoring {currency_symbol}'] = {
            'task': 'lib.cryptointegrator.tasks.check_for_scoring',
            'schedule': 60,
            'args': (),
            'options': {
                'expires': 10,
                'queue': currency_symbol,
            }
        }

    return schedule
