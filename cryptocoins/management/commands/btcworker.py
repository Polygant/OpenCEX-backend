from cryptocoins.utils.base_worker import BaseWorker
from cryptocoins.coins.btc.service import BTCCoinService


class Command(BaseWorker):
    SERVICE_CLASS = BTCCoinService
