import datetime

from django.conf import settings

from lib.services.blockcypher_client import BlockcypherClient
from cryptocoins.cold_wallet_stats.base_stats_handler import BaseStatsHandler


class BtcStatsHandler(BaseStatsHandler):
    ADDRESS = settings.BTC_SAFE_ADDR
    CURRENCY = 'BTC'

    def get_calculated_data(self, current_dt, previous_dt, previous_entry=None, topups_dict=None, withdrawals_dict=None,
                            *args, **kwargs) -> dict:

        client = BlockcypherClient()
        address_txs = client.get_transactions(self.ADDRESS)

        cold_out = 0
        prev_balance = 0
        #prev_balance = previous_entry.stats.get(f'{self.get_db_field_prefix()}_cold_balance')
        current_balance = 0

        for tx in address_txs:
            if tx['confirmed'] > current_dt:
                break

            if tx['spent'] and previous_dt <= tx['confirmed'] < current_dt:
                cold_out += tx['value']

            current_balance = tx['ref_balance']

            if tx['confirmed'] < previous_dt:
                prev_balance = current_balance

        delta = prev_balance + self.get_topups(topups_dict) - cold_out - current_balance
        data = {
            'cold_balance': current_balance,
            # 'prev_balance': prev_balance,
            'cold_out': cold_out,
            'cold_delta': delta,
            'topups': self.get_topups(topups_dict),
            'withdrawals': self.get_withdrawals(withdrawals_dict),
        }
        data_to_save = self.generate_output_dict(**data)
        return data_to_save