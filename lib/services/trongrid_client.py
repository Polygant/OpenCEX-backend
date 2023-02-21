import datetime
import logging
import random
import time

import pytz
import requests
from django.conf import settings
from tronpy import keys

from cryptocoins.utils.tokens import get_token_contract_address
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class TrongridClient:
    def __init__(self):
        self.url = 'https://api.trongrid.io/v1/'
        self.use_api_key = True
        self.sess = requests.session()

        api_key = settings.TRONGRID_API_KEY
        if isinstance(api_key, (str,)):
            self._api_keys = [api_key]
        elif isinstance(api_key, (list,)) and api_key:
            self._api_keys = api_key
        else:
            self._api_keys = api_key.copy()

    def _make_request(self, uri=''):
        if self.use_api_key:
            self.sess.headers['TRON-PRO-API-KEY'] = self.random_api_key

        resp = requests.get(f'{self.url}{uri}')
        if resp.status_code == 403 and b'Exceed the user daily usage' in resp.content:
            log.warning(resp.json().get('Error', 'rate limit!'))
            self._handle_rate_limit()
            return self._make_request(uri)

        resp.raise_for_status()
        return resp.json()

    @property
    def random_api_key(self):
        return random.choice(self._api_keys)

    def _handle_rate_limit(self):
        if len(self._api_keys) > 1:
            self._api_keys.remove(self.sess.headers["TRON-PRO-API-KEY"])
        else:
            log.warning('Please add as-many API-Keys in HTTPProvider')
            time.sleep(0.9)

    def get_address_tx_transfers(self, address, min_timestamp=None):
        limit = 200
        uri = f'accounts/{address}/transactions?limit={limit}&order_by=block_timestamp,asc'
        if min_timestamp:
            uri += f'&min_timestamp={min_timestamp}'
        txs = self._make_request(uri)
        all_txs = []

        while 1:
            all_txs.extend(txs['data'])
            if len(txs['data']) >= limit:
                fingerprint = txs['meta']['fingerprint']
                paged_uri = f'{uri}&fingerprint={fingerprint}'
                time.sleep(1)
                txs = self._make_request(paged_uri)
                # print(txs)
            else:
                break

        ret_txs = []

        for tx in all_txs:
            if tx['ret'][0]['contractRet'] != 'SUCCESS':
                continue

            raw_contract_data = tx['raw_data']['contract'][0]
            if raw_contract_data['type'] not in ['TransferContract', 'TriggerSmartContract']:
                continue

            value_data = raw_contract_data['parameter']['value']

            if raw_contract_data['type'] == 'TriggerSmartContract':
                data = {
                    'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(tx['block_timestamp'] / 1000))),
                    'hash': tx['txID'],
                    'from': keys.to_base58check_address(value_data['owner_address']),
                    'to': '',
                    'fee': 0,
                    'amount': to_decimal(tx.get('energy_fee', 0) / 10 ** 6),
                    'value': to_decimal(tx.get('energy_fee', 0) / 10 ** 6),
                }
            else:
                data = {
                    'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(tx['block_timestamp'] / 1000))),
                    'hash': tx['txID'],
                    'from': keys.to_base58check_address(value_data['owner_address']),
                    'to': keys.to_base58check_address(value_data['to_address']),
                    'fee': 0,
                    'amount': to_decimal(value_data['amount'] / 10**6),
                    'value': to_decimal(value_data['amount'] / 10**6) + to_decimal(tx['ret'][0].get('fee', 0) / 10**6),
                }

            ret_txs.append(data)

        return ret_txs

    def get_address_token_transfers(self, address, currency_code, min_timestamp=None):
        contract_address = get_token_contract_address(currency_code, 'TRX')
        limit = 200
        uri = f'accounts/{address}/transactions/trc20?limit={limit}&order_by=block_timestamp,asc' \
              f'&contract_address={contract_address}'
        if min_timestamp:
            uri += f'&min_timestamp={min_timestamp}'
        tokens = self._make_request(uri)
        all_tokens = []

        while 1:
            all_tokens.extend(tokens['data'])
            if len(tokens['data']) >= limit:
                fingerprint = tokens['meta']['fingerprint']
                paged_uri = f'{uri}&fingerprint={fingerprint}'
                time.sleep(1)
                tokens = self._make_request(paged_uri)
                # print(tokens)
            else:
                break

        all_tokens = list([{
            'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(t['block_timestamp']/1000))),
            'hash': t['transaction_id'],
            'from': t['from'],
            'to': t['to'],
            'value': to_decimal(int(t['value']) / 10 ** 6),
            'amount': to_decimal(int(t['value']) / 10 ** 6),
        } for t in all_tokens])

        return all_tokens
