from typing import List

from django.conf import settings

from cryptocoins.monitoring.base_monitor import BaseMonitor
from lib.helpers import to_decimal
from lib.services.blockstream_client import BlockstreamClient


class BtcMonitor(BaseMonitor):
    CURRENCY = 'BTC'
    BLOCKCHAIN_CURRENCY = 'BTC'
    ACCUMULATION_TIMEOUT = 60 * 60
    DELTA_AMOUNT = to_decimal(0.00001)
    SAFE_ADDRESS = settings.BTC_SAFE_ADDR
    OFFSET_SECONDS = 15

    def get_address_transactions(self, address, *args, **kwargs) -> List:
        """
        Get address transactions from third-party services like etherscan, blockstream etc
        """
        client = BlockstreamClient()
        outs_list = client.get_address_outs(address)
        return outs_list
