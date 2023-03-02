import datetime

from django.conf import settings
from tronpy import Tron

from lib.helpers import to_decimal
from lib.services.trongrid_client import TrongridClient
from cryptocoins.cold_wallet_stats.base_stats_handler import BaseStatsHandler


class TrxStatsHandler(BaseStatsHandler):
    ADDRESS = settings.TRX_SAFE_ADDR
    CURRENCY = 'TRX'

    def get_calculated_data(self, current_dt, previous_dt, previous_entry=None, topups_dict=None, withdrawals_dict=None,
                            *args, **kwargs) -> dict:

        prev_balance = 0
        if previous_entry:
            prev_balance = previous_entry.stats.get(f'trx_cold_balance', 0)

        client = TrongridClient()
        node_client = Tron()
        last_dt_timestamp = int(previous_dt.timestamp() * 1000)

        current_balance = node_client.get_account_balance(self.ADDRESS)
        address_txs = client.get_address_tx_transfers(self.ADDRESS, last_dt_timestamp)

        cold_out = 0

        for tx in address_txs:
            if tx['created'] > current_dt:
                break

            if tx['from'] == self.ADDRESS:
                if previous_dt <= tx['created'] < current_dt:
                    cold_out += tx['value']

        prev_balance = to_decimal(prev_balance)
        topups_amount = to_decimal(self.get_topups(topups_dict))
        cold_out = to_decimal(cold_out)
        current_balance = to_decimal(current_balance)

        delta = prev_balance + topups_amount - cold_out - current_balance

        data = {
            'cold_balance': current_balance,
            # 'prev_balance': prev_balance,
            'cold_out': cold_out,
            'cold_delta': delta,
            'topups': topups_amount,
            'withdrawals': to_decimal(self.get_withdrawals(withdrawals_dict))
        }
        data_to_save = self.generate_output_dict(**data)
        return data_to_save