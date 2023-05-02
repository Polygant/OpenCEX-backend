import datetime
import logging

import pytz
import requests
from django.conf import settings
from web3 import Web3

from core.consts.currencies import ERC20_CURRENCIES
from core.currency import Currency
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class EtherscanClient:
    def __init__(self):
        self.url = 'https://api.etherscan.io/api?'

    def _make_request(self, uri=''):
        res = {}
        try:
            res = requests.get(f'{self.url}{uri}&apikey={settings.ETHERSCAN_KEY}')
            res = res.json()
        except Exception as e:
            log.exception('Can\'t fetch data from blockchain.info')
        return res

    def get_address_tx_transfers(self, address, start_block=0, end_block=99999999, only_eth_txs=True):
        uri = f'module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&sort=asc'
        txs = self._make_request(uri)['result']
        all_txs = []

        while 1:
            all_txs.extend(txs)
            if len(txs) >= 10000:
                last_tx = txs[-1]
                uri = f'module=account&action=txlist&address={address}&startblock={last_tx["blockNumber"]}&endblock={end_block}&sort=asc'
                txs = self._make_request(uri)['result']
            else:
                break

        all_txs = list([{
            'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(t['timeStamp']))),
            'hash': t['hash'],
            'from': t['from'],
            'to': t['to'],
            'fee': to_decimal(Web3.from_wei(int(t['gasPrice']) * int(t['gasUsed']), 'ether')),
            'amount': to_decimal(Web3.from_wei(int(t['value']), 'ether')),
            'value': to_decimal(Web3.from_wei(int(t['value']) + int(t['gasPrice']) * int(t['gasUsed']), 'ether')),
        } for t in all_txs])

        if only_eth_txs:
            all_txs = list([t for t in all_txs if t['amount'] > 0])
        return all_txs

    def get_token_params(self, currency_code):
        return ERC20_CURRENCIES.get(Currency.get(currency_code))

    def get_address_token_transfers(self, address, currency_code, start_block=0, end_block=99999999):
        token_params = self.get_token_params(currency_code)
        if not token_params:
            raise Exception(f'Token {currency_code} not registered')

        contract_address = token_params.contract_address
        contract_decimals = token_params.decimal_places

        uri = f'module=account&action=tokentx&address={address}&startblock={start_block}' \
              f'&endblock={end_block}&sort=asc&contractaddress={contract_address}'
        tokens = self._make_request(uri)['result']
        all_tokens = []

        while 1:
            all_tokens.extend(tokens)
            if len(tokens) >= 10000:
                last_tx = tokens[-1]
                uri = f'module=account&action=tokentx&address={address}&startblock={last_tx["blockNumber"]}' \
                      f'&endblock={end_block}&sort=asc&contractaddress={contract_address}'
                tokens = self._make_request(uri)['result']
            else:
                break

        all_tokens = list([{
            'created': pytz.UTC.localize(datetime.datetime.fromtimestamp(int(t['timeStamp']))),
            'hash': t['hash'],
            'from': t['from'],
            'to': t['to'],
            'value': to_decimal(int(t['value']) / 10 ** contract_decimals),
            'amount': to_decimal(int(t['value']) / 10 ** contract_decimals),
        } for t in all_tokens if t['contractAddress'] == contract_address.lower()])

        return all_tokens
