from decimal import Decimal
from enum import Enum
from typing import NamedTuple, List, Union


class OrderSide(Enum):
    BUY = 1
    SELL = 2

class OrderType(Enum):
    LIMIT = 1
    AUTO = 2


class OrderStruct(NamedTuple):
    price: Decimal
    quantity: Decimal
    quantity_left: Decimal = 0.0
    side: OrderSide = OrderSide.BUY
    id: Union[str, int, None] = None
    order_type: OrderType = OrderType.LIMIT
    otc_percent: float = 0.0
    is_bot: bool = False

    def copy(self, price=None, quantity=None, side=None, order_type=None, otc_percent=None):
        return OrderStruct(
            price=price or self.price,
            quantity=quantity or self.quantity,
            side=side or self.side,
            order_type=order_type or self.order_type,
            id=self.id,
            quantity_left=self.quantity_left,
            otc_percent=otc_percent or self.otc_percent
        )

    # def __str__(self):
    #     return f'Price: {self.price} Quantity: {self.quantity}, Quantity left: {self.quantity_left}, ' \
    #            f'Side: {self.side}, Order type: {self.order_type}'
    #
    # def __repr__(self) -> str:
    #     return f'Price: {self.price} Quantity: {self.quantity}, Quantity left: {self.quantity_left}, ' \
    #            f'Side: {self.side}, Order type: {self.order_type}'


class AmountPriceStruct(NamedTuple):
    price: float = 0.0
    amount: float = 0.0

    def __str__(self):
        return f'price: {self.price} amount: {self.amount}'

    def __repr__(self):
        return self.__str__()


class OrderBookEntryStruct(NamedTuple):
    lowest_sell: AmountPriceStruct
    highest_buy: AmountPriceStruct

    # def __str__(self):
    #     return f'Lowest sell: {self.lowest_sell};  Highest buy: {self.highest_buy}'
    #
    # def __repr__(self):
    #     return self.__str__()
