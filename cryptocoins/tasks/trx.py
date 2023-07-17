import logging
from celery import shared_task
from django.conf import settings
from cryptocoins.coins.trx.tron import tron_client

log = logging.getLogger(__name__)


@shared_task
def get_trc20_unit_price():
    try:
        chain_parameters = tron_client.get_chain_parameters()
        for param in chain_parameters:
            if param['key'] == 'getEnergyFee':
                settings.TRC20_ENERGY_UNIT_PRICE = param['value']
                break

    except Exception:
        log.exception('Can\'t getting chain parameters')
