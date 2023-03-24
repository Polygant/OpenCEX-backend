from decimal import Decimal
from typing import Dict, Union

from core.pairs import Pair


class BaseDataSource:
    NAME: str
    MAX_DEVIATION: Union[int, float, Decimal]

    @property
    def data(self) -> Dict[Pair, Decimal]:
        raise NotImplementedError

    def get_latest_prices(self) -> Dict[Pair, Decimal]:
        raise NotImplementedError
