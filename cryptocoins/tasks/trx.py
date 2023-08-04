import logging
from celery import shared_task
from django.conf import settings
from django.db.models import QuerySet

from core.models.inouts.withdrawal import PENDING as WR_PENDING, FAILED_RESULTS
from core.utils.withdrawal import get_withdrawal_requests_by_status
from cryptocoins.coins.trx.utils import get_transaction_status

log = logging.getLogger(__name__)


@shared_task
def get_trc20_unit_price():
    try:
        from cryptocoins.coins.trx.tron import tron_client

        chain_parameters = tron_client.get_chain_parameters()
        for param in chain_parameters:
            if param['key'] == 'getEnergyFee':
                settings.TRC20_ENERGY_UNIT_PRICE = param['value']
                break

    except Exception:
        log.exception('Can\'t getting chain parameters')


@shared_task
def retry_unknown_withdrawals() -> None:
    # Process only unknown withdrawal request for Tron
    from cryptocoins.coins.trx.tron import TronHandler

    def check_withdrawal_request(unknown_withdrawals: QuerySet) -> None:
        for withdrawal in unknown_withdrawals:
            tx_id = withdrawal.txid
            receipt = get_transaction_status(tx_id)
            if (
                "receipt" in receipt
                and "result" in receipt["receipt"]
                and receipt["receipt"]["result"] in FAILED_RESULTS
            ):
                withdrawal.fail()
                log.error('Failed - %s', receipt['receipt']['result'])
            else:
                withdrawal.state = WR_PENDING
                withdrawal.save(update_fields=['state', 'updated'])

    coin_unknown_withdrawals = get_withdrawal_requests_by_status([TronHandler.CURRENCY], status=WR_PENDING)
    tokens_unknown_withdrawals = get_withdrawal_requests_by_status(
        TronHandler.TOKEN_CURRENCIES,
        blockchain_currency=TronHandler.CURRENCY.code,
        status=WR_PENDING,
    )

    check_withdrawal_request(coin_unknown_withdrawals)
    check_withdrawal_request(tokens_unknown_withdrawals)
