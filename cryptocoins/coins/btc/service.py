from collections import defaultdict
from decimal import Decimal

from cryptos import Bitcoin, apply_multisignatures, serialize
from django.conf import settings

from core.models.cryptocoins import UserWallet
from core.models.inouts.fees_and_limits import FeesAndLimits
from cryptocoins.cache import sat_per_byte_cache
from cryptocoins.coin_service import BitCoreCoinServiceBase
from cryptocoins.coins.btc import BTC_CURRENCY
from cryptocoins.exceptions import CoinServiceError, TransferAmountLowError
from cryptocoins.models import AccumulationTransaction
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.models.scoring import ScoringSettings
from cryptocoins.scoring.manager import ScoreManager
from cryptocoins.tasks.scoring import process_deffered_deposit
from cryptocoins.utils.btc import btc2sat
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal


class BTCCoinService(BitCoreCoinServiceBase):
    CURRENCY = BTC_CURRENCY
    node_config = settings.NODES_CONFIG['btc']
    cold_wallet_address = settings.BTC_SAFE_ADDR
    const_fee = 0.00003
    CRYPTO_COIN = Bitcoin()

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

        estimated_tx_size = self.get_multi_tx_size(
            self.prepare_inputs(keeper_unspent),
            self.prepare_outs(tx_outputs),
            keeper_wallet.private_key,
            private_key,
            keeper_wallet.redeem_script,
        )
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
            redeem_script=keeper_wallet.redeem_script
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
                'tx_hash': item['txid'],
                'tx_pos': item['vout'],
                'output': item['txid'] + ':' + str(item['vout']),
                'value': int(btc2sat(to_decimal(item['amount'])))
            }
            for item in inputs
        ]

    def multi_tx_sign(self, inputs: list, outputs: list, private_key: str, private_key_s: str, redeem_script: str):
        """
        make transaction and sign with two prv key
        """
        tx_obj = self.crypto_coin.mktx(inputs, outputs)

        for i in range(0, len(tx_obj['ins'])):
            inp = tx_obj['ins'][i]
            segwit = False
            try:
                if address := inp['address']:
                    segwit = self.crypto_coin.is_native_segwit(address)
            except (IndexError, KeyError):
                pass
            sig1 = self.crypto_coin.multisign(tx_obj, i, redeem_script, private_key_s)
            sig3 = self.crypto_coin.multisign(tx_obj, i, redeem_script, private_key)
            tx_obj = apply_multisignatures(tx_obj, i, redeem_script, sig1, sig3, segwit=segwit)

        return serialize(tx_obj)

    def multi_transfer(self, inputs: list, outputs: list, private_key: str, private_key_s: str, redeem_script: str):
        """
        make transaction,sign with two prv key and send raw_tx
        """
        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))
        raw_tx = self.multi_tx_sign(inputs, outputs, private_key, private_key_s, redeem_script)
        tx_id = self.rpc.sendrawtransaction(raw_tx)
        self.log.info('Sent TX: %s', tx_id)

        return tx_id

    def get_multi_tx_size(self, inputs: list, outputs: list, private_key: str, private_key_s: str, redeem_script: str):
        """
        get size raw_tx in bytes
        """
        raw_tx = self.multi_tx_sign(inputs, outputs, private_key, private_key_s, redeem_script)
        tx_decode = self.rpc.decoderawtransaction(raw_tx)
        return tx_decode.get('size')

    def check_tx_for_deposit(self, tx_data):
        tx_id = tx_data['txid']
        outputs_amount = defaultdict(Decimal)

        # get total amount for each address
        for addr, amount in self.parse_tx_outputs(tx_data):
            outputs_amount[addr] += amount

        output_address = ', '.join(outputs_amount)
        accumulation_transaction: AccumulationTransaction = AccumulationTransaction.objects.filter(
            tx_hash=tx_id,
            tx_state=AccumulationTransaction.STATE_PENDING,
        ).first()

        if accumulation_transaction:
            addr = accumulation_transaction.wallet_transaction.wallet.address
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
            accumulation_transaction.complete()

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

    def accumulate_deposit(self, wallet_transaction, inputs_dict, private_keys_dict):
        #private_keys = {}
        item = inputs_dict.get(wallet_transaction.tx_hash)
        if not item:
            return
        #private_keys[item['txid'] + ':' + str(item['vout'])] = private_keys_dict[item['address']]
        private_keys_dict[item['txid'] + ':' + str(item['vout'])] = private_keys_dict[item['address']]
        total_amount = wallet_transaction.amount

        accumulation_address = wallet_transaction.external_accumulation_address or self.get_accumulation_address(total_amount)
        accumulation_amount = 0

        try:
            tx_id, accumulation_amount = self.transfer_to([item], accumulation_address, total_amount,  private_keys_dict)
        except TransferAmountLowError:
            wallet_transaction.set_balance_too_low()
            tx_id = None

        if tx_id:
            AccumulationDetails.objects.create(
                currency=BTC_CURRENCY,
                txid=tx_id,
                from_address=item['address'],
                to_address=accumulation_address,
            )
            AccumulationTransaction.objects.create(
                wallet_transaction=wallet_transaction,
                amount=accumulation_amount,
                tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
                tx_hash=tx_id,
            )
            wallet_transaction.set_accumulation_in_progress()
        self.log.info(f'Accumulation to {accumulation_address} succeeded')

    def accumulate(self):
        """
        We need to check if tx is bad
        """
        self.log.info('Starting accumulation: %s', self.currency.code)

        to_accumulate = self.get_accumulation_ready_wallet_transactions()
        to_accumulate_from_addresses = [w.wallet.address for w in to_accumulate]

        if not to_accumulate:
            self.log.warning('There are no addresses to accumulate')
            return

        inputs = self.get_unspent(addresses=to_accumulate_from_addresses)
        inputs_dict = {i['txid']: i for i in inputs}

        private_keys_dict = dict(UserWallet.objects.filter(
            currency=self.currency,
            address__in=to_accumulate_from_addresses,
        ).values_list(
            'address',
            'private_key'
        ))

        private_keys_dict = {
            address: AESCoderDecoder(settings.CRYPTO_KEY).decrypt(private_key) for address, private_key in private_keys_dict.items()
        }

        for wallet_transaction in to_accumulate:
            self.accumulate_deposit(wallet_transaction, inputs_dict, private_keys_dict)


        to_accumulate = self.get_external_accumulation_ready_wallet_transactions()
        to_accumulate_from_addresses = [w.wallet.address for w in to_accumulate]

        if not to_accumulate:
            self.log.warning('There are no addresses to accumulate')
            return

        inputs = self.get_unspent(addresses=to_accumulate_from_addresses)
        inputs_dict = {i['txid']: i for i in inputs}

        private_keys_dict = dict(UserWallet.objects.filter(
            currency=self.currency,
            address__in=to_accumulate_from_addresses,
        ).values_list(
            'address',
            'private_key'
        ))

        private_keys_dict = {
            address: AESCoderDecoder(settings.CRYPTO_KEY).decrypt(private_key) for address, private_key in private_keys_dict.items()
        }

        for wallet_transaction in to_accumulate:
            self.accumulate_deposit(wallet_transaction, inputs_dict, private_keys_dict)


    def transfer(self, inputs: list, outputs: dict, private_keys: dict):
        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))

        inputs = self.prepare_inputs(inputs)
        outputs = self.prepare_outs(outputs)
        tx_hex = self.crypto_coin.mktx(inputs, outputs)
        signed_tx = self.crypto_coin.signall(tx_hex, private_keys)
        signed_tx_s = serialize(signed_tx)
        tx_id = self.rpc.sendrawtransaction(signed_tx_s)
        self.log.info('Sent TX: %s', tx_id)

        return tx_id

    def get_tx_size(self, inputs: list, outputs: dict, private_keys: dict):

        inputs = self.prepare_inputs(inputs)
        outputs = self.prepare_outs(outputs)
        tx_hex = self.crypto_coin.mktx(inputs, outputs)
        signed_tx_without_fee = self.crypto_coin.signall(tx_hex, private_keys)
        signed_tx_without_fee_s = serialize(signed_tx_without_fee)

        tx_decode = self.rpc.decoderawtransaction(signed_tx_without_fee_s)
        return tx_decode.get('size')

    def transfer_to(self, inputs: list, address_to: str, amount: Decimal, private_keys: dict) -> [str, Decimal]:

        pre_outputs = {
            address_to: amount
        }

        tx_size = self.get_tx_size(inputs, pre_outputs, private_keys)
        transfer_fee = self.get_transfer_fee(tx_size)

        transfer_amount = amount - transfer_fee

        self.log.info('Estimated transfer fee: %s fee[%s] size[%s]', self.currency.code, transfer_fee, tx_size)

        if transfer_amount <= 0:
            self.log.info('Transfer amount too low after fee apply: %s', transfer_amount)
            raise TransferAmountLowError

        outputs = {
            address_to: transfer_amount
        }

        inputs = self.prepare_inputs(inputs)
        outputs = self.prepare_outs(outputs)
        tx_hex = self.crypto_coin.mktx(inputs, outputs)
        signed_tx = self.crypto_coin.signall(tx_hex, private_keys)
        signed_tx_s = serialize(signed_tx)

        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))
        tx_id = self.rpc.sendrawtransaction(signed_tx_s)
        self.log.info('Sent TX: %s', tx_id)

        return tx_id, transfer_amount
