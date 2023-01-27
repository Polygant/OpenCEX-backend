from decimal import Decimal
from typing import Union

from lib.helpers import to_decimal


def get_amount_from_base_denomination(value: Union[str, int, float, Decimal], decimal_places: int) -> Decimal:
    """
    Get fraction amount from int with custom decimal places count
    """
    return to_decimal(value) / 10 ** decimal_places


def get_base_denomination_from_amount(value: Union[str, int, float, Decimal], decimal_places: int) -> int:
    """
    Get int
    """
    return int(to_decimal(value) * 10 ** decimal_places)