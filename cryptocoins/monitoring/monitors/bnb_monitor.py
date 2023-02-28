from typing import List

from django.conf import settings

from cryptocoins.monitoring.base_monitor import BaseMonitor
from lib.helpers import to_decimal
from lib.services.bscscan_client import BSCscanClient


class BnbMonitor(BaseMonitor):
    CURRENCY = 'BNB'
    BLOCKCHAIN_CURRENCY = 'BNB'
    ACCUMULATION_TIMEOUT = 60 * 10
    DELTA_AMOUNT = to_decimal(0.01)
    SAFE_ADDRESS = settings.BNB_SAFE_ADDR
    OFFSET_SECONDS = 16

    def get_address_transactions(self, address, *args, **kwargs) -> List:
        """
        Get address transactions from third-party services like etherscan, blockstream etc
        """
        client = BSCscanClient()
        tx_list = client.get_address_tx_transfers(address)
        return tx_list
