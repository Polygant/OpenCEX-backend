import logging

from cryptocoins.monitoring.monitors.bep20_monitor import UsdtBnbMonitor
from cryptocoins.monitoring.monitors.bnb_monitor import BnbMonitor
from cryptocoins.monitoring.monitors.btc_monitor import BtcMonitor
from cryptocoins.monitoring.monitors.erc20_monitor import UsdtEthMonitor
from cryptocoins.monitoring.monitors.eth_monitor import EthMonitor
from cryptocoins.monitoring.monitors.trc20_monitor import UsdtTrxMonitor
from cryptocoins.monitoring.monitors.trx_monitor import TrxMonitor
from cryptocoins.monitoring.monitors.tenz_monitor import TenzMonitor

log = logging.getLogger(__name__)

MONITORS = {
    'BTC': BtcMonitor,
    'TENZ': TenzMonitor,
    'ETH': EthMonitor,
    'TRX': TrxMonitor,
    'BNB': BnbMonitor,
    'USDTTRX': UsdtTrxMonitor,
    'USDTETH': UsdtEthMonitor,
    'USDTBNB': UsdtBnbMonitor,
}


class MonitoringProcessor:
    monitors: dict = MONITORS

    @classmethod
    def process(cls, currency):
        Monitor = MONITORS.get(currency)
        if not Monitor:
            raise Exception(f'Monitor not found for {currency}')

        monitor = Monitor()
        log.info(f'Monitoring: processing {monitor.CURRENCY} {monitor.BLOCKCHAIN_CURRENCY}')
        monitor.mark_wallet_transactions()
