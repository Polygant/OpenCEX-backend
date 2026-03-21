from cryptocoins.utils.base_worker import BaseWorker
from cryptocoins.coins.tenz.service import TENZCoinService


class Command(BaseWorker):
    SERVICE_CLASS = TENZCoinService 