import datetime
import logging

import pytz
import requests

from lib.helpers import to_decimal

log = logging.getLogger(__name__)

TIMEOUT = 5

class BlockstreamClient:
    def __init__(self):
        # ['http://btcnode.coin-cap.pro/', 'https://blockstream.info/api/']
        self.url = 'http://btcnode.coin-cap.pro/'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}')
            res = res.json()
        except Exception as e:
            log.exception('Can\'t fetch data from btcnode.coin-cap.pro')
        return res

    def get_address_txs(self, address, created_dt=None):
        resource = f'address/{address}/txs/chain'
        all_txs = []
        while 1:
            txs = self._make_request(resource)
            formatted_txs = list([format_confirmed_transaction(tx, address=address) for tx in txs])
            all_txs.extend(formatted_txs)
            last_seen_tx = formatted_txs[-1]

            if len(formatted_txs) > 25 and created_dt and created_dt < last_seen_tx['created']:
                resource = f'address/{address}/txs/chain/{last_seen_tx["hash"]}'
            else:
                break
        return all_txs

    def get_address_outs(self, address, created_dt=None):
        txs = self.get_address_txs(address, created_dt)
        outs = []
        for tx in txs:
            if not tx['spent']:
                continue
            for out in tx['vout']:
                out['created'] = tx['created']
                out['hash'] = tx['hash']
                out['fee'] = tx['fee']
                out['from'] = address
                out['to'] = out['address']
                out['value'] = out['value'] + out['fee']
                outs.append(out)
        return outs


def sat_to_btc(sat):
    return to_decimal(sat) / to_decimal(10**8)


def format_confirmed_transaction(tx, address):
    tx_data = {
        'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(tx['status']['block_time']))),
        'hash': tx['txid'],
        'vin': list([stats_from_inout(vin) for vin in tx['vin']]),
        'vout': list([stats_from_inout(vout, True) for vout in tx['vout']]),
        'fee': sat_to_btc(tx.get('fee', 0)),
        'spent': False
    }
    input_addresses = list(input['address'] for input in tx_data['vin'])
    if address in input_addresses:
        tx_data['spent'] = True
    return tx_data


def stats_from_inout(in_out, out=False):
    data = {
        'address': None,
        'value': 0
    }
    if not out:
        in_out = in_out.get('prevout')
    if in_out:
        data['address'] = in_out.get('scriptpubkey_address')
        data['value'] = sat_to_btc(in_out.get('value', 0))
    return data


