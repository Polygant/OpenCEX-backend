import logging
from typing import Any, Dict

import backoff
import math
import trontxsize
from django.conf import settings
from tronpy import Tron
from tronpy.abi import trx_abi


log = logging.getLogger(__name__)

TRC20_FEE_LIMIT = settings.TRC20_FEE_LIMIT
TRX_NET_FEE = settings.TRX_NET_FEE
TRC20_ENERGY_UNIT_PRICE = settings.TRC20_ENERGY_UNIT_PRICE
TRC20_FEE_LIMIT_FACTOR = settings.TRC20_FEE_LIMIT_FACTOR
RECEIPT_RETRY_INTERVAL = settings.RECEIPT_RETRY_INTERVAL
RECEIPT_RETRY_ATTEMPTS = settings.RECEIPT_RETRY_ATTEMPTS


def is_valid_tron_address(address):
    try:
        res = Tron.is_address(address)
        return res
    except:
        return False


def get_latest_tron_block_num(*args):
    client = Tron()
    return client.get_latest_block_number()


def get_energy_fee(energy_needed: float, energy_limit: float, energy_used: float) -> int:
    current_account_energy = energy_limit - energy_used
    energy_fee = max(energy_needed - current_account_energy, 0) * TRC20_ENERGY_UNIT_PRICE
    return math.ceil(energy_fee)


def get_bandwidth_fee(tx: Dict[str, Any], address: str) -> int:
    try:
        from cryptocoins.coins.trx.tron import tron_client

        account_info = tron_client.get_account_resource(addr=address)
        free_net_limit = account_info.get('freeNetLimit', 0)
        net_limit = account_info.get('NetLimit', 0)
        free_net_used = account_info.get('freeNetUsed', 0)
        net_used = account_info.get('NetUsed', 0)
        total_bandwidth = free_net_limit + net_limit
        total_bandwidth_used = net_used + free_net_used
        current_account_bandwidth = total_bandwidth - total_bandwidth_used

        how_many_bandwidth_need = trontxsize.get_tx_size({'signature': tx['signature'], 'raw_data': tx['raw_data']})
        if current_account_bandwidth < how_many_bandwidth_need:
            bandwidth_fee = (how_many_bandwidth_need + 3) * 1000
        else:
            bandwidth_fee = 0
        # bandwidth_fee = max((how_many_bandwidth_need - current_account_bandwidth) * 1000, 0)
        return math.ceil(bandwidth_fee * TRC20_FEE_LIMIT_FACTOR)  # TRX_NET_FEE
    except Exception:
        log.exception('An error occurred while calculating bandwidth_fee')
        return TRX_NET_FEE


def get_fee_limit(tx: Dict[str, Any], owner_address: str, to_address: str, amount: int, contract_address: str) -> int:
    """
    Calculations are based on an article from Stack Overflow
    (https://stackoverflow.com/questions/67172564/how-to-estimate-trc20-token-transfer-gas-fee)
    """

    try:
        from cryptocoins.coins.trx.tron import tron_client

        parameter = trx_abi.encode_abi(['address', 'uint256'], [to_address, amount]).hex()
        account_info = tron_client.get_account_resource(addr=owner_address)
        energy_data = tron_client.trigger_constant_contract(
            owner_address=owner_address,
            contract_address=contract_address,
            function_selector='transfer(address,uint256)',
            parameter=parameter
        )
        required_energy = energy_data['energy_used']
        energy_limit = account_info.get('EnergyLimit', 0)
        energy_used = account_info.get('EnergyUsed', 0)

        energy_fee = get_energy_fee(required_energy, energy_limit, energy_used)
        bandwidth_fee = get_bandwidth_fee(tx, owner_address)

        return math.ceil((bandwidth_fee + energy_fee) * TRC20_FEE_LIMIT_FACTOR)
    except Exception:
        log.exception('An error occurred while calculating transaction fee')
        return TRC20_FEE_LIMIT


@backoff.on_exception(backoff.constant, Exception, max_tries=RECEIPT_RETRY_ATTEMPTS, interval=RECEIPT_RETRY_INTERVAL)
def wait_receipt(res) -> Dict:
    return res.wait()


@backoff.on_exception(backoff.constant, Exception, max_tries=RECEIPT_RETRY_ATTEMPTS, interval=RECEIPT_RETRY_INTERVAL)
def get_transaction_status(tx_id: str) -> Dict:
    from cryptocoins.coins.trx.tron import tron_client
    return tron_client.get_transaction_info(tx_id)
