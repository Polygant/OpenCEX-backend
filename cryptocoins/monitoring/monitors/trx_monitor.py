from typing import List

from django.conf import settings

from cryptocoins.monitoring.base_monitor import BaseMonitor
from lib.helpers import to_decimal
from lib.services.trongrid_client import TrongridClient


class TrxMonitor(BaseMonitor):
    CURRENCY = 'TRX'
    BLOCKCHAIN_CURRENCY = 'TRX'
    ACCUMULATION_TIMEOUT = 60 * 10
    DELTA_AMOUNT = to_decimal(settings.TRX_NET_FEE / 10**6)
    SAFE_ADDRESS = settings.TRX_SAFE_ADDR
    OFFSET_SECONDS = 15

    def get_address_transactions(self, address, *args, **kwargs) -> List:
        """
        Get address transactions from third-party services like etherscan, blockstream etc
        """
        client = TrongridClient()
        tx_list = client.get_address_tx_transfers(address)
        tx_list = [tx for tx in tx_list if tx['to']]
        return tx_list
