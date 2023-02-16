from collections import defaultdict
from decimal import Decimal

from cryptos import Bitcoin, apply_multisignatures
from django.conf import settings

from core.models.cryptocoins import UserWallet
from core.models.inouts.fees_and_limits import FeesAndLimits
from cryptocoins.cache import sat_per_byte_cache
from cryptocoins.coin_service import BitCoreCoinServiceBase
from cryptocoins.coins.btc import BTC_CURRENCY
from cryptocoins.exceptions import CoinServiceError
from cryptocoins.models import ScoringSettings
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.scoring.manager import ScoreManager
from cryptocoins.tasks.scoring import process_deffered_deposit
from cryptocoins.utils.btc import btc2sat
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal


class BTCCoinService(BitCoreCoinServiceBase):
    currency = BTC_CURRENCY
    node_config = settings.NODES_CONFIG['btc']
    cold_wallet_address = settings.BTC_SAFE_ADDR
    const_fee = 0.00001
    crypto_coin = Bitcoin()

    def get_transfer_fee(self, size):
        # fee = to_decimal(size / 1000) * to_decimal(0.0002)
        # return to_decimal(max(fee, self.const_fee))
        s_p_b = self.get_sat_per_byte()
        fee = to_decimal(size * s_p_b / 10 ** 8)
        self.log.info(f'Fee = {s_p_b} Sat/b * {size} bytes / 10**8 = {fee} BTC')
        return to_decimal(max(fee, to_decimal(self.const_fee)))

    def get_sat_per_byte(self):
        return sat_per_byte_cache.get('bitcoin', settings.SAT_PER_BYTES_MIN_LIMIT)

    def send_from_keeper(self, outputs, *args, **kwargs):
        private_key = kwargs.get('private_key')
        keeper_wallet = kwargs.get('keeper_wallet') or self.get_keeper_wallet()
        keeper_unspent = kwargs.get('keeper_unspent') or self.get_unspent(addresses=[keeper_wallet.address])
        keeper_balance = self.get_balance_from_unspent(keeper_unspent)

        tx_outputs = {}
        for item in outputs:
            if item.address in tx_outputs:
                tx_outputs[item.address] += to_decimal(item.amount)
            else:
                tx_outputs[item.address] = to_decimal(item.amount)

        # need to fill chargeback amount later
        tx_outputs[keeper_wallet.address] = 0

        estimated_tx_size = self.estimate_tx_size(len(keeper_unspent), len(tx_outputs))
        # 1 because the previous function already calculated the size
        estimated_tx_size += self.estimate_script_sig_size(1, 3)
        transfer_fee = self.get_transfer_fee(estimated_tx_size)

        outputs_sum = sum(tx_outputs.values())
        self.log.info('%s withdrawals outputs sum: %s', self.currency.code, outputs_sum)

        chargeback_amount = keeper_balance - transfer_fee - outputs_sum
        self.log.info('%s chargeback amount: %s', self.currency.code, chargeback_amount)

        if chargeback_amount < 0:
            self.log.error('Unable to process withdrawals, chargeback after fee less than 0')
            raise CoinServiceError('Unable to process withdrawals, chargeback after fee less than 0')

        tx_outputs[keeper_wallet.address] = chargeback_amount

        return self.multi_transfer(
            inputs=self.prepare_inputs(keeper_unspent),
            outputs=self.prepare_outs(tx_outputs),
            private_key=keeper_wallet.private_key,
            private_key_s=private_key,
            redeemScript=keeper_wallet.redeem_script
        )

    @staticmethod
    def prepare_outs(outs: dict) -> list:
        return [
            {
                'address': address,
                'value': int(btc2sat(to_decimal(amount)))
            }
            for address, amount in outs.items()
        ]

    @staticmethod
    def prepare_inputs(inputs: list) -> list:
        return [
            {
                'address': item['address'],
                'output': item['txid']+':'+str(item['vout']),
                'value': int(btc2sat(to_decimal(item['amount'])))
            }
            for item in inputs
        ]

    def multi_transfer(self, inputs: list, outputs: list, private_key: str, private_key_s: str, redeemScript: str):
        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))
        tx = self.crypto_coin.mktx(inputs, outputs)
        for i in range(0, len(tx['ins'])):
            sig1 = self.crypto_coin.multisign(tx, i, redeemScript, private_key_s)
            sig3 = self.crypto_coin.multisign(tx, i, redeemScript, private_key)
            tx = apply_multisignatures(tx, i, redeemScript, sig1, sig3)

        tx_id = self.rpc.sendrawtransaction(tx)
        self.log.info('Sent TX: %s', tx_id)

        return tx_id

    def check_tx_for_deposit(self, tx_data):
        tx_id = tx_data['txid']
        outputs_amount = defaultdict(Decimal)

        # get total amount for each address
        for addr, amount in self.parse_tx_outputs(tx_data):
            outputs_amount[addr] += amount

        input_addresses = self.parse_tx_inputs(tx_data)
        output_address = ', '.join(outputs_amount)

        #process accumulations
        for addr in input_addresses:
            if addr not in self.get_users_addresses():
                continue

            self.log.info(f'Found accumulation from {addr} to {output_address}')
            accumulation_details = AccumulationDetails.objects.filter(
                txid=tx_id,
                from_address=addr
            ).first()
            if not accumulation_details:
                AccumulationDetails.objects.create(
                    currency=BTC_CURRENCY,
                    txid=tx_id,
                    from_address=addr,
                    to_address=output_address,
                )
            else:
                accumulation_details.to_address = output_address
                accumulation_details.complete()

        # process only our addresses
        for addr, amount in outputs_amount.items():
            if addr not in self.get_users_addresses():
                continue

            if amount < FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE):
                self.log.info('Amount %s less than min deposit limit', amount)
                continue

            # self.process_deposit(tx_id, addr, amount)
            if ScoreManager.need_to_check_score(tx_id, addr, amount, self.currency.code):
                defer_time = ScoringSettings.get_deffered_scoring_time(self.currency.code)
                process_deffered_deposit.apply_async((tx_id, addr, amount, self.currency.code), queue='btc', countdown=defer_time)
            else:
                self.log.info('Tx amount too low for scoring')
                self.process_deposit(tx_id, addr, amount)


    def accumulate(self):
        """
        We need to check if tx is bad
        """
        self.log.info('Starting accumulation: %s', self.currency.code)

        accumulation_ready_addresses_qs = self.get_accumulation_ready_addresses()
        addresses = [a.address for a in accumulation_ready_addresses_qs]
        to_accumulate_addresses = self.filter_accumulation_ready_addresses(addresses)
        if not to_accumulate_addresses:
            self.log.warning('There are no addresses to accumulate')
            return
        inputs = self.get_unspent(addresses=to_accumulate_addresses)

        # check if spendable
        checked_inputs = []
        checked_txs_hashes = []

        # todo: get only needed keys
        private_keys_dict = dict(UserWallet.objects.filter(
            currency=self.currency,
            address__in=list(i['address'] for i in inputs)
        ).values_list(
            'address',
            'private_key'
        ))

        private_keys_dict = {
            address: AESCoderDecoder(settings.CRYPTO_KEY).decrypt(private_key) for address, private_key in private_keys_dict.items()
        }

        private_keys = {}

        for item in inputs:
            result = self.rpc.gettxout(
                item['txid'],
                item['vout'],
            )
            if not result:
                continue

            checked_inputs.append(item)
            checked_txs_hashes.append(item['txid'])
            private_keys[item['txid'] + ':' + str(item['vout'])] = private_keys_dict[item['address']]

        total_amount = sum([to_decimal(i['amount']) for i in checked_inputs])

        if total_amount < self.min_accumulation_balance or total_amount == 0:
            self.log.info('Total balance too low for accumulation: %s %s',
                          self.currency.code, total_amount)
            return

        self.log.info('Total accumulation balance: %s %s', self.currency.code, total_amount)

        estimated_tx_size = self.estimate_tx_size(len(checked_inputs), 1)
        transfer_fee = self.get_transfer_fee(estimated_tx_size)
        self.log.info('Estimated transfer fee: %s %s', self.currency.code, transfer_fee)
        accumulation_amount = total_amount - transfer_fee

        if accumulation_amount <= 0:
            self.log.info('Accumulation balance too low after fee apply: %s', accumulation_amount)
            return

        accumulation_address = self.get_accumulation_address(accumulation_amount)

        outputs = {
            accumulation_address: accumulation_amount,
        }

        txid = self.transfer(checked_inputs, outputs, private_keys)
        if txid:
            for item in checked_inputs:
                AccumulationDetails.objects.create(
                    currency=BTC_CURRENCY,
                    txid=txid,
                    from_address=item['address'],
                    to_address=accumulation_address,
                )
            self.log.info(f'Accumulation to {accumulation_address} succeeded')
        accumulation_ready_addresses_qs.update(accumulation_made=True)


    def transfer(self, inputs: list, outputs: dict, private_keys: dict):
        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))

        inputs = self.prepare_inputs(inputs)
        outputs = self.prepare_outs(outputs)
        tx_hex = self.crypto_coin.mktx(inputs, outputs)
        signed_tx = self.crypto_coin.signall(tx_hex, private_keys)

        # if not signed_tx['complete']:
        #     self.log.error('Unable to sign TX')
        #     return

        tx_id = self.rpc.sendrawtransaction(signed_tx)
        self.log.info('Sent TX: %s', tx_id)

        return tx_id
