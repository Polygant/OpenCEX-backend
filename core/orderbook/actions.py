import time
from typing import Optional

import simplejson
from django.conf import settings
from django.core.cache import cache

from core.orderbook.helpers import group_by_precision

from lib.utils import threaded_daemon
from exchange.notifications import stack_notificator


class Actions(object):
    STACK_TIMEOUT = settings.STACK_UPDATE_PERIOD  # in seconds
    STACK_DOWN_TIMEOUT = settings.STACK_DOWN_TIMEOUT  # in seconds
    STACK_DOWN_MULTI = settings.STACK_DOWN_MULTI  # in seconds
    UPDATER_SLEEP = 0.1

    def __init__(self, book):
        self.book = book
        self.last_stack_update = self.STACK_TIMEOUT + 1
        self.last_cache_update = 0
        self.stack_cache_update_enabled = True
        self.down_multiplier = 1
        self.down_send_time: Optional[float] = None

    def start_updater(self):
        self.updater_thread = self.stack_cache_updater()

    def set_cache(self):
        if not self.stack_cache_update_enabled:
            return

        data = self.book.export(settings.STACK_EXPORT_LIMIT)
        pair_code = data['pair']
        key = f'stack:{pair_code}'
        cache.set(key, simplejson.dumps(data), timeout=None)
        self.notify_stack(data)

        groped_by_precisions_stack_data = group_by_precision(data['pair'], data)
        for precision, grouped_data in groped_by_precisions_stack_data.items():
            key = f'stack:{pair_code}:{precision}'
            cache.set(key, simplejson.dumps(grouped_data), timeout=None)
            self.notify_stack(grouped_data, precision=precision)

        self.last_cache_update = time.time()

    def set_cache_update(self, enabled=True):
        self.stack_cache_update_enabled = enabled

    def send_alert(self, pair):
        from lib.notifications import send_telegram_message
        self.down_send_time = time.time()
        self.down_multiplier = self.down_multiplier * self.STACK_DOWN_MULTI
        self.book.logger.info(f'Stack: {pair} down! at {time.ctime(self.last_stack_update)}')
        send_telegram_message(f'Stack: {pair} down! at {time.ctime(self.last_stack_update)}')

    @threaded_daemon
    def stack_cache_updater(self):
        from core.consts.pairs import BTC_USDT
        from core.models.inouts.pair import Pair
        while True:
            time.sleep(self.UPDATER_SLEEP)

            pair: str = self.book.pair
            btc_usdt_pair: Pair = Pair.get(BTC_USDT)

            if (
                btc_usdt_pair.code.upper() == pair.upper()
            ) and (
                (time.time() - self.last_stack_update) > (self.STACK_DOWN_TIMEOUT * self.down_multiplier)
            ) and (
                not self.down_send_time or (time.time() > self.down_send_time + (self.STACK_DOWN_TIMEOUT * self.down_multiplier))
            ):
                self.send_alert(pair)

            if self.last_cache_update > self.last_stack_update:
                continue

            c1 = (time.time() - self.last_stack_update) > self.STACK_TIMEOUT
            c2 = (self.last_stack_update - self.last_cache_update) > self.STACK_TIMEOUT

            if c1 or c2:
                self.down_multiplier = 1
                self.set_cache()

    def notify_stack(self, data, precision=None):
        stack_notificator.notify(data, pair_name=self.book.pair, precision=precision)

    def order_processed(self, order):
        self.last_stack_update = time.time()

    def order_cancelled(self, order):
        self.last_stack_update = time.time()
