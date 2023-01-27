import logging
from collections import defaultdict, namedtuple
from decimal import Decimal

import cachetools.func
import pywallet
import requests
from bitcoinrpc.authproxy import AuthServiceProxy
from django.conf import settings
from django.db import transaction
from pywallet.utils.keys import PublicKey

from core.currency import Currency
from core.models.cryptocoins import UserWallet
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_min_accumulation_balance
from core.utils.inouts import get_withdrawal_fee
from cryptocoins.exceptions import CoinServiceError
from cryptocoins.models.keeper import Keeper
from cryptocoins.utils import commons
from cryptocoins.utils.btc import pubkey_to_address
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal
from lib.utils import memcache_lock

WalletAccount = namedtuple('WalletAccount', ['address', 'private_key', 'redeem_script'])
TxOutput = namedtuple('TxOutput', ['address', 'amount'])


class CoinServiceBase:
    currency: Currency = None
    cold_wallet_address: str = None
    default_block_id_delta = 100

    def __init__(self) -> None:
        self.log = logging.getLogger(f'{self.__module__}.{self.__class__.__name__}')

        if self.currency is None:
            raise ValueError('currency must be set')

        self.currency = commons.ensure_currency(self.currency)

    @property
    def withdrawal_fee(self):
        return get_withdrawal_fee(self.currency, self.currency)

    @property
    def min_accumulation_balance(self):
        return get_min_accumulation_balance(self.currency)

    def get_current_block_id(self):
        raise NotImplementedError

    def get_block_transactions(self, block_id):
        raise NotImplementedError

    def check_tx_for_deposit(self, tx_data):
        raise NotImplementedError

    def get_wallet_balance(self, address):
        raise NotImplementedError

    def get_keeper_balance(self):
        raise NotImplementedError

    def accumulate(self):
        raise NotImplementedError

    def process_withdrawals(self):
        raise NotImplementedError

    def create_new_wallet(self, label=''):
        raise NotImplementedError

    def create_userwallet(self, user_id, is_new=False):
        wallet = UserWallet.objects.filter(
            user_id=user_id,
            currency=self.currency,
            merchant=False,
        ).first()

        if not is_new and wallet is not None:
            self.log.info('Found %s wallet for user %s', self.currency.code, user_id)
            return wallet

        self.log.info('Create new %s wallet for user %s', self.currency.code, user_id)
        wallet_account = self.create_new_wallet()
        wallet = UserWallet.objects.create(
            user_id=user_id,
            currency=self.currency,
            address=wallet_account.address,
            private_key=AESCoderDecoder(settings.CRYPTO_KEY).encrypt(
                wallet_account.private_key
            ),
            blockchain_currency=self.currency
        )

        return wallet

    @cachetools.func.ttl_cache(ttl=5)
    def get_keeper_wallet(self) -> WalletAccount:
        keeper = Keeper.objects.filter(
            currency=self.currency,
        ).select_related(
            'user_wallet',
        ).only(
            'user_wallet__address',
            'user_wallet__private_key',
        ).first()

        if keeper is None:
            raise ValueError(f'Keeper for {self.currency.code} not found')

        return WalletAccount(
            address=keeper.user_wallet.address,
            private_key=AESCoderDecoder(settings.CRYPTO_KEY).decrypt(
                keeper.user_wallet.private_key
            ),
            redeem_script=keeper.extra.get('redeem_script')
        )

    @cachetools.func.ttl_cache(ttl=5)
    def get_users_addresses(self, exclude_disabled_accumulations=False):
        qs = UserWallet.objects.filter(
            currency=self.currency,
            keeper=None,
        ).exclude(
            user_id=None,
        ).values_list(
            'address',
            flat=True,
        )
        if exclude_disabled_accumulations:
            qs = qs.exclude(block_type=UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION)
        return list(qs)

    def get_accumulation_ready_addresses(self):
        from cryptocoins.models import TransactionInputScore
        return TransactionInputScore.objects.filter(
            currency=self.currency,
            scoring_state__in=[TransactionInputScore.SCORING_STATE_DISABLED,
                               TransactionInputScore.SCORING_STATE_SMALL_AMOUNT,
                               TransactionInputScore.SCORING_STATE_OK],
        )

    def filter_accumulation_ready_addresses(self, addresses: list):
        addresses = UserWallet.objects.filter(
            address__in=addresses,
        ).exclude(
            block_type=UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION,
        ).values_list('address', flat=True)
        return list(addresses)

    @transaction.atomic
    def process_new_blocks(self):
        """
        Process new blocks to check deposits
        """
        with memcache_lock(f'{self.currency}_lock', f'{self.currency}_lock', 60) as acquired:
            if acquired:
                current_block_id = self.get_current_block_id()
                last_processed_block_id = commons.load_last_processed_block_id(
                    self.currency,
                    default=current_block_id - self.default_block_id_delta,
                )

                if current_block_id == last_processed_block_id:
                    self.log.debug('Nothing to process')
                    return

                blocks_to_process = list(range(
                    last_processed_block_id + 1,
                    current_block_id + 1,
                ))

                self.log.info('Need to process %s blocks count: %s',
                              self.currency.code, blocks_to_process)

                # usually not many blocks
                for block_id in blocks_to_process:
                    self.log.info('Processing %s %s block', self.currency.code, block_id)
                    for tx_data in self.get_block_transactions(block_id):
                        self.check_tx_for_deposit(tx_data)

                commons.store_last_processed_block_id(self.currency, current_block_id)
                return
        self.log.warning(f'{self.currency} process_new_blocks task already works')

    def get_withdrawal_requests(self):
        return WithdrawalRequest.crypto_to_process(currency=self.currency).order_by('created')

    def get_sufficient_withdrawal_requests(self, limit: Decimal):
        """
        Get withdrawal requests which keeper has sufficient balance to process
        """
        withdrawal_requests = self.get_withdrawal_requests()
        result = []
        total_amount = to_decimal(0)

        for item in withdrawal_requests:
            if (total_amount + item.amount) <= limit:
                total_amount += item.amount
                result.append(item)

            else:
                break

        return result

    def process_deposit(self, tx_hash, address, amount, is_scoring_ok=True):
        self.log.info('Processing deposit %s %s %s %s', self.currency, amount, address, tx_hash)
        wallet = UserWallet.objects.filter(
            currency=self.currency,
            address=address,
        ).first()

        if wallet is None:
            self.log.error('Wallet %s does not exist', address)
            return

        wallet_transaction = WalletTransactions.objects.filter(
            wallet_id=wallet.id,
            tx_hash=tx_hash,
            currency=self.currency,
            amount=amount,
        ).first()

        if wallet_transaction is not None:
            self.log.warning('Deposit %s %s for address %s already been processed, skipping',
                             self.currency.code, amount, address)
            return

        # make deposit
        WalletTransactions.objects.create(
            wallet_id=wallet.id,
            tx_hash=tx_hash,
            currency=self.currency,
            amount=amount,
            state=WalletTransactions.STATE_NOT_CHECKED if is_scoring_ok else WalletTransactions.STATE_BAD_DEPOSIT,
        )
        self.log.info('Deposit %s %s for address %s processed', self.currency.code, amount, address)


class BitCoreCoinServiceBase(CoinServiceBase):
    """
    Base service for BitCore based coins e.g. BTC, LTC, BCH
    """
    node_config: dict = None

    def __init__(self) -> None:
        super().__init__()

        if self.node_config is None:
            raise ValueError('node_config attribute must be set')

        if self.cold_wallet_address is None:
            raise ValueError('cold_wallet_address attribute must be set')

        if self.withdrawal_fee is None:
            raise ValueError('withdrawal_fee attribute must be set')

        self.rpc_url = 'http://{username}:{password}@{host}:{port}'.format(
            **self.node_config, timeout=60)

    def get_transfer_fee(self, size):
        raise NotImplementedError

    @property
    def rpc(self) -> AuthServiceProxy:
        """
        Recreate instance each time due sharing problems
        """
        return AuthServiceProxy(self.rpc_url)

    @property
    @cachetools.func.ttl_cache(ttl=5)
    def node_version(self) -> int:
        return self.rpc.getnetworkinfo()['version']

    @cachetools.func.ttl_cache(ttl=5)
    def get_users_private_keys(self):
        return list(UserWallet.objects.filter(
            currency=self.currency,
            keeper=None,
        ).exclude(
            private_key='-',
        ).values_list(
            'private_key',
            flat=True,
        ))

    def import_address(self, address: str, label: str = ''):
        self.rpc.importaddress(address, str(label), False)
        self.log.info('Address %s %s imported', self.currency, address)

    def create_new_wallet(self, label: str = '') -> WalletAccount:
        """
        Create new wallet address and key and import address to node
        """
        self.log.info('Create new %s wallet', self.currency.code)
        wallet = pywallet.wallet.Wallet.new_random_wallet(
            network=self.currency.code.upper(),
        )
        address = wallet.to_address()
        private_key = wallet.export_to_wif()

        if isinstance(private_key, bytes):
            private_key = private_key.decode('utf-8')

        self.import_address(address, label=label)

        return WalletAccount(
            address=address,
            private_key=private_key,
            redeem_script=None,
        )

    def get_unspent(self, addresses: list = None):
        if addresses is None:
            addresses = []

        return self.rpc.listunspent(1, 9999999, addresses)

    def get_users_unspent(self, exclude_disabled_accumulations=False):
        addresses = self.get_users_addresses(exclude_disabled_accumulations)

        if not addresses:
            self.log.info('Have no user addresses for %s', self.currency.code)
            return []

        return self.get_unspent(addresses=addresses)

    def get_wallet_balance(self, address: str) -> Decimal:
        unspent = self.get_unspent(addresses=[address])
        return self.get_balance_from_unspent(unspent)

    def get_users_total_balance(self) -> Decimal:
        unspent = self.get_users_unspent()
        return self.get_balance_from_unspent(unspent)

    def get_keeper_balance(self) -> Decimal:
        keeper_wallet = self.get_keeper_wallet()
        return self.get_wallet_balance(keeper_wallet.address)

    def accumulate(self):
        self.log.info('Starting accumulation: %s', self.currency.code)

        inputs = self.get_users_unspent()
        # check if spendable
        checked_inputs = []
        for item in inputs:
            result = self.rpc.gettxout(
                item['txid'],
                item['vout'],
            )
            if not result:
                continue

            checked_inputs.append(item)

        # total_amount = self.get_users_total_balance()
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

        # todo: get only needed keys
        # private_keys = self.get_users_private_keys()
        private_keys = list(UserWallet.objects.filter(
            currency=self.currency,
            address__in=list(i['address'] for i in checked_inputs)
        ).values_list(
            'private_key',
            flat=True,
        ))
        private_keys = [AESCoderDecoder(settings.CRYPTO_KEY).decrypt(i) for i in private_keys]

        outputs = {
            self.cold_wallet_address: accumulation_amount,
        }

        self.transfer(checked_inputs, outputs, private_keys)

    def transfer(self, inputs: list, outputs: dict, private_keys: list):
        self.log.info('Make transfer %s in -> %s out', len(inputs), len(outputs))
        tx_hex = self.rpc.createrawtransaction(inputs, outputs)
        signed_tx = self._sign_transaction(tx_hex, private_keys)

        if not signed_tx['complete']:
            self.log.error('Unable to sign TX')
            return

        tx_id = self.rpc.sendrawtransaction(signed_tx['hex'])
        self.log.info('Sent TX: %s', tx_id)

        return tx_id

    @property
    def accumulation_min_balance(self):
        return FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.MIN_VALUE)

    @property
    def deposit_min_amount(self):
        return FeesAndLimits.get_limit(self.currency.code, FeesAndLimits.DEPOSIT, FeesAndLimits.MIN_VALUE)

    def get_block_transactions(self, block_id):
        block_hash = self.rpc.getblockhash(block_id)
        return self.rpc.getblock(block_hash, 2)['tx']

    def check_tx_for_deposit(self, tx_data):
        tx_id = tx_data['txid']
        outputs_amount = defaultdict(Decimal)

        # get total amount for each address
        for addr, amount in self.parse_tx_outputs(tx_data):
            outputs_amount[addr] += amount

        # process only our addresses
        for addr, amount in outputs_amount.items():
            if addr not in self.get_users_addresses():
                continue

            if amount < self.deposit_min_amount and amount < self.accumulation_min_balance:
                self.log.info('Amount %s less than min deposit limit', amount)
                continue

            self.process_deposit(tx_id, addr, amount)

    def get_current_block_id(self):
        return self.rpc.getblockcount()

    def get_last_network_block_id(self):
        response = requests.get('https://blockchain.info/latestblock')
        response.raise_for_status()

        return response.json().get('height', 0)
        # return self.rpc.getblockchaininfo().get('headers', 0)

    def process_withdrawals(self, *args, **kwargs):
        """
        Process withdrawal requests
        """
        self.log.info('Processing %s withdrawals', self.currency.code)
        keeper_wallet = self.get_keeper_wallet()
        keeper_unspent = self.get_unspent(addresses=[keeper_wallet.address])
        keeper_balance = self.get_balance_from_unspent(keeper_unspent)
        self.log.info('%s keeper balance: %s', self.currency.code, keeper_balance)
        sufficient_requests = self.get_sufficient_withdrawal_requests(limit=keeper_balance)

        if not sufficient_requests:
            self.log.debug('Nothing to withdraw or %s keeper balance too low', self.currency.code)
            raise CoinServiceError(
                'Nothing to withdraw or %s keeper balance too low' % self.currency.code)

        self.log.info('Enough balance for requests count: %s', len(sufficient_requests))

        outputs = []

        for item in sufficient_requests:
            final_amount = item.amount - self.withdrawal_fee
            dest_address = item.data['destination']
            outputs.append(TxOutput(address=dest_address, amount=final_amount))

        tx_id = self.send_from_keeper(
            outputs,
            *args,
            **kwargs,
            keeper_wallet=keeper_wallet,
            keeper_unspent=keeper_unspent,
        )

        if tx_id is None:
            self.log.error('Unable to withdraw %s', self.currency.code)
            raise CoinServiceError('Unable to withdraw %s' % self.currency.code)

        for item in sufficient_requests:
            item.txid = tx_id
            item.our_fee_amount = self.withdrawal_fee
            item.save()
            item.complete()

        self.log.info('Withdrawal completed')

    def send_from_keeper(self, outputs, *args, **kwargs):
        keeper_wallet = kwargs.get('keeper_wallet') or self.get_keeper_wallet()
        keeper_unspent = kwargs.get('keeper_unspent') or self.get_unspent(
            addresses=[keeper_wallet.address])
        password = kwargs.get('password')
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
        transfer_fee = self.get_transfer_fee(estimated_tx_size)

        outputs_sum = sum(tx_outputs.values())
        self.log.info('%s withdrawals outputs sum: %s', self.currency.code, outputs_sum)

        chargeback_amount = keeper_balance - transfer_fee - outputs_sum
        self.log.info('%s chargeback amount: %s', self.currency.code, chargeback_amount)

        if chargeback_amount < 0:
            self.log.error('Unable to process withdrawals, chargeback after fee less than 0')
            raise CoinServiceError(
                'Unable to process withdrawals, chargeback after fee less than 0')

        tx_outputs[keeper_wallet.address] = chargeback_amount

        private_key = keeper_wallet.private_key
        if password:
            private_key = AESCoderDecoder(password).decrypt(private_key)

        return self.transfer(
            inputs=keeper_unspent,
            outputs=tx_outputs,
            private_keys=[private_key]
        )

    def _sign_transaction(self, tx_hex, private_keys):
        # backward compatibility
        if self.node_version >= 170000:
            return self.rpc.signrawtransactionwithkey(tx_hex, private_keys, [])
        else:
            return self.rpc.signrawtransaction(tx_hex, [], private_keys)

    @staticmethod
    def estimate_tx_size(inputs_num: int, outputs_num: int) -> int:
        return inputs_num * 148 + outputs_num * 34 + 10

    @staticmethod
    def estimate_script_sig_size(required_num: int, address_num: int) -> int:
        return 5 + 74*address_num + 34*required_num

    @staticmethod
    def parse_tx_outputs(tx_data):
        outputs = []

        for item in tx_data['vout']:
            address = None

            if 'addresses' in item['scriptPubKey']:
                address = item['scriptPubKey']['addresses'][0]

            if 'address' in item['scriptPubKey']:
                address = item['scriptPubKey']['address']

            if not address:
                continue

            outputs.append((
                address,
                item['value'],
            ))

        return outputs

    def parse_tx_inputs(self, tx_data):
        input_addresses = []
        for vin in tx_data['vin']:
            try:
                pubkey = vin['scriptSig'].get('asm', '').split(' ')[1]
                address = pubkey_to_address(pubkey)
                input_addresses.append(address)
            except Exception:
                # skip
                pass
                # self.log.warning('[-] Error parsing tx ' + tx_data['txid'])
        return input_addresses

    @staticmethod
    def script_sig_to_addr(script_sig):
        """
        {
         "asm": "asm",  (string) asm
         "hex": "hex"   (string) hex
        }
        """
        pub_key = script_sig['asm'].split(' ')[1]

        return PublicKey.from_hex_key(pub_key).to_address()

    @staticmethod
    def get_balance_from_unspent(unspent):
        return sum([to_decimal(i['amount']) for i in unspent])
