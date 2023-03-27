from django.conf import settings

from cryptocoins.cold_wallet_stats.base_stats_handler import BaseStatsHandler
from lib.services.bscscan_client import BSCscanClient


class Bep20StatsHandler(BaseStatsHandler):
    ADDRESS = settings.BNB_SAFE_ADDR
    BLOCKCHAIN_CURRENCY = 'BNB'

    def get_calculated_data(self, current_dt, previous_dt, previous_entry=None, topups_dict=None, withdrawals_dict=None,
                            *args, **kwargs) -> dict:

        client = BSCscanClient()
        address_txs = client.get_address_token_transfers(
            self.ADDRESS, self.CURRENCY)

        cold_out = 0
        prev_balance = 0
        current_balance = 0
        for tx in address_txs:
            if tx['created'] > current_dt:
                break

            if tx['from'].lower() == self.ADDRESS.lower():
                if previous_dt <= tx['created'] < current_dt:
                    cold_out += tx['value']
                current_balance -= tx['value']
            else:
                current_balance += tx['amount']

            if tx['created'] < previous_dt:
                prev_balance = current_balance

        delta = prev_balance + \
            self.get_topups(topups_dict) - cold_out - current_balance

        data = {
            'cold_balance': current_balance,
            # 'prev_balance': prev_balance,
            'cold_out': cold_out,
            'cold_delta': delta,
            'topups': self.get_topups(topups_dict),
            'withdrawals': self.get_withdrawals(withdrawals_dict)
        }
        data_to_save = self.generate_output_dict(**data)
        return data_to_save


class UsdtBnbStatsHandler(Bep20StatsHandler):
    CURRENCY = 'USDT'
