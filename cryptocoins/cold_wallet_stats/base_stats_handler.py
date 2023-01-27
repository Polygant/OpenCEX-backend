import logging
from lib.helpers import to_decimal


log = logging.getLogger(__name__)


class BaseStatsHandler:
    ADDRESS = ''
    CURRENCY = ''
    BLOCKCHAIN_CURRENCY = ''

    def __init__(self):
        log.info(f'Prepare {self.CURRENCY}{self.BLOCKCHAIN_CURRENCY} stats handler')

    @classmethod
    def get_db_field_prefix(cls):
        res = cls.CURRENCY
        if cls.BLOCKCHAIN_CURRENCY:
            res += f'_{cls.BLOCKCHAIN_CURRENCY}'
        return res.lower()

    def get_topups(self, topups_dict):
        if not topups_dict:
            return to_decimal(0)
        currency = f'{self.CURRENCY}_{self.BLOCKCHAIN_CURRENCY or self.CURRENCY}'
        return to_decimal(topups_dict.get(currency, 0) or 0)

    def get_withdrawals(self, withdrawals_dict):
        return self.get_topups(withdrawals_dict)

    def get_calculated_data(self, current_dt, previous_dt, previous_entry=None, topups_dict=None, withdrawals_dict=None,
                            *args, **kwargs) -> dict:
        raise NotImplementedError

    def generate_output_dict(self, **kwargs):
        res_dict = {}
        for k, v in kwargs.items():
            if type(v) in [int, float]:
                v = to_decimal(v)
            res_dict[f'{self.get_db_field_prefix()}_{k}'] = v
        return res_dict
