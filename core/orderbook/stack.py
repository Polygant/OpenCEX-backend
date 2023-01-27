import logging

from sortedcontainers import SortedListWithKey

ASC = 0  # возрастает
DESC = 1  # убывает

logger = logging.getLogger(__name__)


class BaseStack(object):
    def __init__(self, direction=ASC):
        self.direction = direction
        self.list = SortedListWithKey(key=self.key)
        self.orders = {}

    def key(self, order):
        if self.direction == ASC:
            return (order.price, order.id)
        else:
            return (-order.price, order.id)

    def add(self, order):
        already_added = order.id in self.orders
        self.orders[order.id] = order  # also acts as update
        if not already_added:
            self.list.add(order)

    def remove(self, order):
        try:
            cached_order = self.orders[order.id]  # get cached order by id, cause order removed by price and id!
            self.list.remove(cached_order)
            del self.orders[order.id]
        except Exception as e:
            logger.info(str(e), exc_info=True)

    def __iter__(self):
        return self.list.__iter__()

    def __contains__(self, key):
        return key in self.orders

    def __getitem__(self, idx):
        return self.list.__getitem__(idx)

    @property
    def top_price(self):
        if not self.list:
            return None
        return self.list[0].price

    def __bool__(self):
        return bool(self.list)

    def __len__(self):
        return self.list.__len__()

    def stack_iter(self):
        for i in self:
            yield (i.price, i.quantity_left)

    def match_price(self, price):
        if self.direction == ASC:
            return price >= self.top_price
        else:
            return price <= self.top_price
