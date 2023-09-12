import logging
import time
from decimal import Decimal
from typing import Type, Union, Optional

from celery import group
from django.core.cache import cache
from eth_abi.codec import ABICodec
from eth_abi.exceptions import NonEmptyPaddingBytes
from eth_abi.registry import registry
from web3 import Web3
from web3._utils.threads import Timeout
from web3.exceptions import TransactionNotFound

from core.models import FeesAndLimits
from core.models.inouts.withdrawal import PENDING as WR_PENDING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee
from core.utils.withdrawal import get_withdrawal_requests_by_status
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.evm.base import BaseEVMCoinHandler
from cryptocoins.exceptions import RetryRequired
from cryptocoins.interfaces.common import BlockchainManager, GasPriceCache, Token, BlockchainTransaction
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from cryptocoins.tasks.evm import (
    check_tx_withdrawal_task,
    process_coin_deposit_task,
    process_tokens_deposit_task,
    check_balance_task,
    accumulate_coin_task,
    accumulate_tokens_task,
    send_gas_task,
)
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal

log = logging.getLogger(__name__)
accumulation_manager = AccumulationManager()
abi_codec = ABICodec(registry)


class Web3Transaction(BlockchainTransaction):
    @classmethod
    def from_node(cls, tx_data) -> Optional['Web3Transaction']:
        tx_hash = tx_data['hash']
        if hasattr(tx_hash, 'hex') and callable(getattr(tx_hash, 'hex')):
            tx_hash = tx_hash.hex()

        try:
            from_addr = Web3.to_checksum_address(tx_data['from'])
        except:
            from_addr = tx_data['from']

        try:
            to_addr = Web3.to_checksum_address(tx_data['to'])
        except KeyError:
            return
        except:
            to_addr = tx_data['to']

        data = {
            'hash': tx_hash,
            'from_addr': from_addr,
            'contract_address': None,
        }

        # Coin
        if tx_data.input == '0x' or not tx_data.input or tx_data.value:
            data.update({
                'to_addr': to_addr,
                'value': tx_data.value,
            })
        # Token
        else:
            data_bytes = Web3.to_bytes(hexstr=tx_data.input)
            if data_bytes[:4] != b'\xa9\x05\x9c\xbb':  # transfer fn
                return

            try:
                token_to_address, amount = abi_codec.decode(['address', 'uint256'], data_bytes[4:])
            except NonEmptyPaddingBytes:
                return
            except Exception as e:
                log.exception('Cant parse transaction')
                return
            data.update({
                'to_addr': Web3.to_checksum_address(token_to_address),
                'contract_address': to_addr,
                'value': amount,
            })
        return cls(data)


class Web3Token(Token):
    DEFAULT_TRANSFER_GAS_LIMIT: int = 100_000
    DEFAULT_TRANSFER_GAS_MULTIPLIER: int = 2

    def get_contract(self):
        return self.client.eth.contract(self.params.contract_address, abi=self.ABI)

    def decode_function_input(self, data: Union[str, bytes]):
        if isinstance(data, str):
            data = Web3.to_bytes(hexstr=data)
        return self.contract.decode_function_input(data)

    def send_token(self, private_key, to_address, amount_in_base_denomination, **kwargs):
        gas = kwargs['gas']
        gas_price = kwargs['gasPrice']
        nonce = kwargs['nonce']

        tx = self.contract.functions.transfer(
            to_address,
            amount_in_base_denomination,
        ).build_transaction({
            'chainId': self.CHAIN_ID,
            'gas': gas,
            'gasPrice': gas_price,
            'nonce': nonce,
        })
        signed_tx = self.client.eth.account.sign_transaction(tx, private_key)

        try:
            tx_hash = self.client.eth.send_raw_transaction(signed_tx.rawTransaction)
        except ValueError:
            log.exception('Unable to send token accumulation TX')
            return
        return tx_hash


class Web3Manager(BlockchainManager):
    GAS_PRICE_CACHE_CLASS: Type[GasPriceCache] = None
    DEFAULT_RECEIPT_WAIT_TIMEOUT: int = 1 * 60
    BASE_DENOMINATION_DECIMALS: int = 18
    CHAIN_ID: int

    def __init__(self, client):
        super(Web3Manager, self).__init__(client)
        self._gas_price_cache = self.GAS_PRICE_CACHE_CLASS(self.client) if self.GAS_PRICE_CACHE_CLASS else None

    def get_latest_block_num(self):
        return self.client.eth.block_number

    def set_gas_price_too_high(self, wallet_transaction):
        wallet_transaction.state = wallet_transaction.STATE_GAS_PRICE_TOO_HIGH
        wallet_transaction.save(update_fields=['state', 'updated'])

    @property
    def accumulation_max_gas_price(self):
        limit = FeesAndLimits.get_limit(self.CURRENCY.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.MAX_GAS_PRICE)
        return Web3.to_wei(limit, 'gwei')

    def is_gas_price_reach_max_limit(self, price_wei):
        gas_price_limit = self.accumulation_max_gas_price
        return gas_price_limit and price_wei >= gas_price_limit

    def get_block(self, block_id):
        return self.client.eth.get_block(block_id, full_transactions=True)

    def get_balance_in_base_denomination(self, address: str):
        return self.client.eth.get_balance(Web3.to_checksum_address(address))

    def get_balance(self, address: str) -> Decimal:
        base_balance = self.get_balance_in_base_denomination(address)
        return self.get_amount_from_base_denomination(base_balance)

    def send_tx(self, private_key, to_address, amount, **kwargs):
        account = self.client.eth.account.from_key(private_key)
        signed_tx = self.client.eth.account.sign_transaction({
            'nonce': kwargs['nonce'],
            'gasPrice': kwargs['gasPrice'],
            'gas': 21000,
            'from': account.address,
            'to': to_address,
            'value': amount,
            'chainId': self.CHAIN_ID,
        },
            private_key,
        )
        # has been sent?
        # withdrawal_tx = bnb_manager.get_transaction(signed_tx.hash)
        # if withdrawal_tx is not None and withdrawal_tx.transactionIndex:
        #     if not bnb_manager.is_valid_transaction(signed_tx.hash):
        #         log.error('TX %s is failed or invalid', withdrawal_tx.hash)
        #         return
        #
        #     else:
        #         log.warning('Withdrawal %s already sent', withdrawal_tx.hash.hex())
        #         return
        try:
            tx_hash = self.client.eth.send_raw_transaction(signed_tx.rawTransaction)
        except ValueError:
            log.exception('Unable to send accumulation TX')
            return
        return tx_hash

    ##### Web3 commons #####
    @property
    def gas_price_cache(self):
        return self._gas_price_cache

    def is_valid_transaction(self, tx_hash: str) -> bool:
        receipt = self.wait_for_transaction_receipt(tx_hash)
        return bool(receipt.status)

    def is_valid_address(self, address: str) -> bool:
        return self.client.is_address(address)

    def get_transaction_receipt(self, tx_hash):
        if not isinstance(tx_hash, str) and hasattr(tx_hash, 'hex'):
            tx_hash = tx_hash.hex()
        try:
            txn_receipt = self.client.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            txn_receipt = None
        return txn_receipt

    def get_transaction(self, tx_hash):
        if not isinstance(tx_hash, str) and hasattr(tx_hash, 'hex'):
            tx_hash = tx_hash.hex()
        try:
            txn_data = self.client.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            txn_data = None
        return txn_data

    def wait_for_transaction_receipt(self, tx_hash, timeout=DEFAULT_RECEIPT_WAIT_TIMEOUT, poll_latency=1):
        """
        Overridden default method from web3.utils.transactions.wait_for_transaction_receipt
        due to unable to specify poll frequency
        """
        if not isinstance(tx_hash, str) and hasattr(tx_hash, 'hex'):
            tx_hash = tx_hash.hex()
        try:
            with Timeout(timeout) as _timeout:
                while True:
                    txn_receipt = self.get_transaction_receipt(tx_hash)
                    if txn_receipt is not None and txn_receipt['blockHash'] is not None:
                        break

                    log.warning(f'Wait for get receipt retry for {tx_hash}')
                    _timeout.sleep(poll_latency)

        except Timeout:
            raise RetryRequired(f'Failed to get receipt for {tx_hash}')

        return txn_receipt

    def wait_for_nonce(self, is_gas=False):
        address = self.get_gas_keeper_wallet().address if is_gas else self.get_keeper_wallet().address
        target_keeper = ['keeper', 'gas_keeper'][is_gas]

        key = f'nonce_{address}_lock'
        #  waiting for release
        log.info(f'Waiting nonce for {target_keeper}')
        while cache.get(key):
            time.sleep(1)

        cache.set(key, True, timeout=300)
        nonce = self.client.eth.get_transaction_count(address)

        log.info(f'Got nonce for {target_keeper}: {nonce}')
        return nonce

    def release_nonce(self, is_gas=False):
        address = self.get_gas_keeper_wallet().address if is_gas else self.get_keeper_wallet().address
        key = f'nonce_{address}_lock'
        cache.delete(key)

    def wait_for_balance_in_base_denomination(self, address, sleep_for=15, attempts=3):
        for i in range(attempts):
            balance = self.get_balance_in_base_denomination(address)
            if balance:
                return balance
            else:
                time.sleep(sleep_for)
        return 0

    def accumulate_dust(self):
        to_address = self.get_gas_keeper_wallet().address
        from_addresses = self.get_currency_and_addresses_for_accumulation_dust()

        for address, currency in from_addresses:
            address_balance = self.get_balance(address)
            if address_balance >= self.MIN_BALANCE_TO_ACCUMULATE_DUST:
                address_balance_wei = self.get_base_denomination_from_amount(address_balance)
                log.info(f'Accumulation {self.CURRENCY} dust from: {address}; Balance: {address_balance}')

                # we want to process our tx faster
                gas_price = self.gas_price_cache.get_price()
                gas_amount = gas_price * self.GAS_CURRENCY
                withdrawal_amount = address_balance_wei - gas_amount

                # in debug mode values can be very small
                if withdrawal_amount <= 0:
                    log.error(f'{self.CURRENCY} withdrawal amount invalid: '
                              f'{self.get_amount_from_base_denomination(withdrawal_amount)}')
                    return

                # prepare tx
                wallet = self.get_user_wallet(currency, address)
                nonce = self.client.eth.get_transaction_count(address)

                tx_hash = self.send_tx(
                    private_key=wallet.private_key,
                    to_address=to_address,
                    amount=withdrawal_amount,
                    nonce=nonce,
                    gasPrice=gas_price,
                )

                if not tx_hash:
                    log.error('Unable to send dust accumulation TX')
                    return

                log.info(f'Accumulation TX {tx_hash.hex()} sent from {address} to {to_address}')


class Web3CommonHandler(BaseEVMCoinHandler):
    CHAIN_ID = None
    W3_CLIENT = None

    @classmethod
    def process_block(cls, block_id):
        started_at = time.time()
        log.info('Processing block #%s', block_id)

        block = cls.COIN_MANAGER.get_block(block_id)

        if block is None:
            log.error('Failed to get block #%s, skip...', block_id)
            # TODO check this
            # raise self.retry(max_retries=10, countdown=1)
            return

        transactions = block.get('transactions', [])

        if len(transactions) == 0:
            log.info('Block #%s has no transactions, skipping', block_id)
            return

        transactions = cls._filter_transactions(transactions, block_id=block_id)
        log.info('Transactions count in block #%s: %s', block_id, len(transactions))

        coin_deposit_jobs = []
        tokens_deposit_jobs = []

        coins_withdrawal_requests_pending = get_withdrawal_requests_by_status([cls.CURRENCY], status=WR_PENDING)
        tokens_withdrawal_requests_pending = get_withdrawal_requests_by_status(
            cls.TOKEN_CURRENCIES,
            blockchain_currency=cls.CURRENCY.code,
            status=WR_PENDING,
        )

        coin_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                                 for i in coins_withdrawal_requests_pending}
        coin_withdrawal_requests_pending_txs = {v: k for k,
                                                         values in coin_withdrawals_dict.items() for v in values}

        tokens_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                                   for i in tokens_withdrawal_requests_pending}
        tokens_withdrawal_requests_pending_txs = {
            v: k for k, values in tokens_withdrawals_dict.items() for v in values}

        check_coin_withdrawal_jobs = []
        check_tokens_withdrawal_jobs = []

        # Withdrawals
        for tx_data in transactions:
            tx = cls.TRANSACTION_CLASS.from_node(tx_data)
            if not tx:
                continue

            # is COIN withdrawal request tx?
            if tx.hash in coin_withdrawal_requests_pending_txs:
                withdrawal_id = coin_withdrawal_requests_pending_txs[tx.hash]
                check_coin_withdrawal_jobs.append(
                    check_tx_withdrawal_task.s(cls.CURRENCY.code, withdrawal_id, tx.as_dict())
                )
                continue

            # is TOKENS withdrawal request tx?
            if tx.hash in tokens_withdrawal_requests_pending_txs:
                withdrawal_id = tokens_withdrawal_requests_pending_txs[tx.hash]
                check_tokens_withdrawal_jobs.append(
                    check_tx_withdrawal_task.s(cls.CURRENCY.code, withdrawal_id, tx.as_dict())
                )
                continue

        user_addresses = set(cls.COIN_MANAGER.get_user_addresses())
        coin_keeper = cls.COIN_MANAGER.get_keeper_wallet()
        coin_gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()

        deposit_addresses = set(user_addresses)
        deposit_addresses.add(cls.SAFE_ADDR)

        # Deposits
        for tx_data in transactions:
            tx = cls.TRANSACTION_CLASS.from_node(tx_data)
            if not tx:
                continue

            if tx.to_addr is None:
                continue

            if tx.to_addr in deposit_addresses:
                # process coin deposit
                if not tx.contract_address:
                    coin_deposit_jobs.append(process_coin_deposit_task.s(cls.CURRENCY.code, tx.as_dict()))
                # process tokens deposit
                else:
                    tokens_deposit_jobs.append(process_tokens_deposit_task.s(cls.CURRENCY.code, tx.as_dict()))

        if coin_deposit_jobs:
            log.info('Need to check %s deposits count: %s', cls.CURRENCY.code, len(coin_deposit_jobs))
            group(coin_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_deposits')

        if tokens_deposit_jobs:
            log.info('Need to check %s TOKENS deposits count: %s', cls.CURRENCY.code, len(tokens_deposit_jobs))
            group(tokens_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_deposits')

        if check_coin_withdrawal_jobs:
            log.info('Need to check %s withdrawals count: %s', cls.CURRENCY.code, len(check_coin_withdrawal_jobs))
            group(check_coin_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        if check_tokens_withdrawal_jobs:
            log.info('Need to check %s TOKENS withdrawals count: %s', cls.CURRENCY.code,
                     len(check_coin_withdrawal_jobs))
            group(check_tokens_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        # check accumulations
        for tx_data in transactions:
            tx = cls.TRANSACTION_CLASS.from_node(tx_data)
            if not tx:
                continue

            # checks only exchange addresses withdrawals
            if tx.from_addr not in user_addresses:
                continue

            # skip txs from keepers
            if tx.from_addr in [coin_keeper.address, coin_gas_keeper.address, cls.SAFE_ADDR]:
                continue

            # checks only if currency flows outside the exchange
            if tx.to_addr in user_addresses:
                continue

            # check TOKENS accumulations
            if tx.contract_address:
                token = cls.COIN_MANAGER.get_token_by_address(tx.contract_address)

                accumulation_details, created = AccumulationDetails.objects.get_or_create(
                    txid=tx.hash,
                    defaults=dict(
                        txid=tx.hash,
                        from_address=tx.from_addr,
                        to_address=tx.to_addr,
                        currency=cls.CURRENCY,
                        token_currency=token.currency,
                        state=AccumulationDetails.STATE_COMPLETED,
                    )
                )
                if not created:
                    log.info(f'Found accumulation {token.currency} from {tx.from_addr} to {tx.to_addr}')
                    accumulation_details.to_address = tx.to_addr
                    accumulation_details.complete()
                else:
                    log.info(f'Unexpected accumulation {token.currency} from {tx.from_addr} to {tx.to_addr}')

            # check coin accumulations
            else:
                accumulation_details, created = AccumulationDetails.objects.get_or_create(
                    txid=tx.hash,
                    defaults=dict(
                        txid=tx.hash,
                        from_address=tx.from_addr,
                        to_address=tx.to_addr,
                        currency=cls.CURRENCY,
                        state=AccumulationDetails.STATE_COMPLETED,
                    )
                )
                if not created:
                    log.info(f'Found accumulation {cls.CURRENCY.code} from {tx.from_addr} to {tx.to_addr}')
                    # Use to_address only from node
                    accumulation_details.to_address = Web3.to_checksum_address(tx.to_addr)
                    accumulation_details.complete()
                else:
                    log.info(f'Unexpected accumulation {cls.CURRENCY.code} from {tx.from_addr} to {tx.to_addr}')

        execution_time = time.time() - started_at
        log.info('Block #%s processed in %.2f sec. (%s TX count: %s, %s TOKENS TX count: %s, WR TX count: %s)',
                 block_id, execution_time, cls.CURRENCY.code, len(coin_deposit_jobs), cls.CURRENCY.code,
                 len(tokens_deposit_jobs), len(check_tokens_withdrawal_jobs) + len(check_coin_withdrawal_jobs))

    @classmethod
    def check_tx_withdrawal(cls, withdrawal_id, tx_data):
        tx = cls.TRANSACTION_CLASS(tx_data)

        withdrawal_request = WithdrawalRequest.objects.filter(
            id=withdrawal_id,
            state=WR_PENDING,
        ).first()

        if withdrawal_request is None:
            log.warning('Invalid withdrawal request state for TX %s', tx.hash)
            return

        withdrawal_request.txid = tx.hash

        if not cls.COIN_MANAGER.is_valid_transaction(tx.hash):
            withdrawal_request.fail()
            return

        withdrawal_request.complete()

    @classmethod
    def withdraw_coin(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        if old_tx_data is None:
            old_tx_data = {}
        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        # todo: handle errors
        address = Web3.to_checksum_address(withdrawal_request.data.get('destination'))
        keeper = cls.COIN_MANAGER.get_keeper_wallet()
        amount_wei = cls.COIN_MANAGER.get_base_denomination_from_amount(withdrawal_request.amount)
        withdrawal_fee_wei = cls.COIN_MANAGER.get_base_denomination_from_amount(
            get_withdrawal_fee(cls.CURRENCY, cls.CURRENCY))
        amount_to_send_wei = amount_wei - withdrawal_fee_wei

        gas_price = cls.COIN_MANAGER.gas_price_cache.get_increased_price(
            old_tx_data.get('gasPrice') or 0)

        # todo: check min limit
        if amount_to_send_wei <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        keeper_balance = cls.COIN_MANAGER.get_balance_in_base_denomination(keeper.address)
        if keeper_balance < (amount_to_send_wei + (gas_price * cls.COIN_MANAGER.GAS_CURRENCY)):
            log.warning(f'Keeper not enough {cls.CURRENCY}, skipping')
            return

        if old_tx_data:
            log.info(f'{cls.CURRENCY} withdrawal transaction to {address} will be replaced')
            tx_data = old_tx_data.copy()
            tx_data['gasPrice'] = gas_price
            if prev_tx_hash and cls.COIN_MANAGER.get_transaction_receipt(prev_tx_hash):
                log.info(f'{cls.CURRENCY} TX {prev_tx_hash} sent. Do not need to replace.')
                return
        else:
            nonce = cls.COIN_MANAGER.wait_for_nonce()
            tx_data = {
                'nonce': nonce,
                'gasPrice': gas_price,
                'gas': cls.COIN_MANAGER.GAS_CURRENCY,
                'from': Web3.to_checksum_address(keeper.address),
                'to': Web3.to_checksum_address(address),
                'value': amount_to_send_wei,
                'chainId': cls.CHAIN_ID,
            }

        private_key = AESCoderDecoder(password).decrypt(keeper.private_key)
        tx_hash = cls.COIN_MANAGER.send_tx(
            private_key=private_key,
            to_address=address,
            amount=amount_to_send_wei,
            nonce=tx_data['nonce'],
            gasPrice=tx_data['gasPrice'],
        )

        if not tx_hash:
            log.error('Unable to send withdrawal TX')
            cls.COIN_MANAGER.release_nonce()
            return

        withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
        withdrawal_txs_attempts.append(tx_hash.hex())

        withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))

        withdrawal_request.state = WR_PENDING
        withdrawal_request.our_fee_amount = cls.COIN_MANAGER.get_amount_from_base_denomination(withdrawal_fee_wei)
        withdrawal_request.save(update_fields=['state', 'updated', 'our_fee_amount', 'data'])
        log.info(f'{cls.CURRENCY} withdrawal TX {tx_hash.hex()} sent')

        # wait tx processed
        try:
            cls.COIN_MANAGER.wait_for_transaction_receipt(tx_hash, poll_latency=2)
            cls.COIN_MANAGER.release_nonce()
        except RetryRequired:
            # retry with higher gas price
            cls.withdraw_coin(withdrawal_request_id, password, old_tx_data=tx_data, prev_tx_hash=tx_hash)

    @classmethod
    def withdraw_tokens(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        if old_tx_data is None:
            old_tx_data = {}

        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        address = Web3.to_checksum_address(withdrawal_request.data.get('destination'))
        currency = withdrawal_request.currency

        token = cls.COIN_MANAGER.get_token_by_symbol(currency)
        send_amount_wei = token.get_base_denomination_from_amount(withdrawal_request.amount)
        withdrawal_fee_wei = token.get_base_denomination_from_amount(token.withdrawal_fee)
        amount_to_send_wei = send_amount_wei - withdrawal_fee_wei
        if amount_to_send_wei <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        gas_price = cls.COIN_MANAGER.gas_price_cache.get_increased_price(
            old_tx_data.get('gasPrice') or 0)

        transfer_gas = token.get_transfer_gas_amount(address, amount_to_send_wei, True)

        keeper = cls.COIN_MANAGER.get_keeper_wallet()
        keeper_coin_balance = cls.COIN_MANAGER.get_balance_in_base_denomination(keeper.address)
        keeper_token_balance = token.get_base_denomination_balance(keeper.address)

        if keeper_coin_balance < gas_price * transfer_gas:
            log.warning(f'Keeper not enough {cls.CURRENCY} for gas, skipping')
            return

        if keeper_token_balance < amount_to_send_wei:
            log.warning(f'Keeper not enough {currency}, skipping')
            return

        log.info('Amount to send: %s, gas price: %s, transfer gas: %s',
                 amount_to_send_wei, gas_price, transfer_gas)

        if old_tx_data:
            log.info('%s withdrawal to %s will be replaced', currency.code, address)
            tx_data = old_tx_data.copy()
            tx_data['gasPrice'] = gas_price
            if prev_tx_hash and cls.COIN_MANAGER.get_transaction_receipt(prev_tx_hash):
                log.info('Token TX %s sent. Do not need to replace.')
                return
        else:
            nonce = cls.COIN_MANAGER.wait_for_nonce()
            tx_data = {
                'chainId': cls.CHAIN_ID,
                'gas': transfer_gas,
                'gasPrice': gas_price,
                'nonce': nonce,
            }

        private_key = AESCoderDecoder(password).decrypt(keeper.private_key)
        tx_hash = token.send_token(private_key, address, amount_to_send_wei, **tx_data)

        if not tx_hash:
            log.error('Unable to send token withdrawal TX')
            cls.COIN_MANAGER.release_nonce()
            return

        withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
        withdrawal_txs_attempts.append(tx_hash.hex())

        withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))
        withdrawal_request.state = WR_PENDING
        withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(withdrawal_fee_wei)

        withdrawal_request.save(update_fields=['state', 'updated', 'our_fee_amount', 'data'])
        log.info('%s withdrawal TX %s sent', currency, tx_hash.hex())

        # wait tx processed
        try:
            cls.COIN_MANAGER.wait_for_transaction_receipt(tx_hash, poll_latency=2)
            cls.COIN_MANAGER.release_nonce()
        except RetryRequired:
            # retry with higher gas price
            cls.withdraw_tokens(withdrawal_request_id, password, old_tx_data=tx_data, prev_tx_hash=tx_hash)

    @classmethod
    def is_gas_need(cls, wallet_transaction):
        acc_tx = accumulation_manager.get_last_gas_deposit_tx(wallet_transaction)
        return not acc_tx

    @classmethod
    def check_balance(cls, wallet_transaction_id):
        """Splits blockchain currency accumulation and token accumulation"""
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address
        currency = wallet_transaction.currency

        # coin
        if currency == cls.CURRENCY:
            wallet_transaction.set_ready_for_accumulation()
            accumulate_coin_task.apply_async(
                [cls.CURRENCY.code, wallet_transaction_id],
                queue=f'{cls.CURRENCY.code.lower()}_accumulations'
            )

        # tokens
        else:
            log.info('Checking %s %s', currency, address)

            if not cls.is_gas_need(wallet_transaction):
                log.info(f'Gas not required for {currency} {address}')
                wallet_transaction.set_ready_for_accumulation()
                accumulate_tokens_task.apply_async(
                    [cls.CURRENCY.code, wallet_transaction_id],
                    queue=f'{cls.CURRENCY.code.lower()}_tokens_accumulations'
                )
            else:
                log.info(f'Gas required for {currency} {address}')
                wallet_transaction.set_gas_required()
                send_gas_task.apply_async(
                    [cls.CURRENCY.code, wallet_transaction_id],
                    queue=f'{cls.CURRENCY.code.lower()}_send_gas'
                )

    @classmethod
    def accumulate_coin(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address

        # recheck balance
        amount = wallet_transaction.amount
        amount_wei = cls.COIN_MANAGER.get_base_denomination_from_amount(amount)

        log.info('Accumulation %s from: %s; Balance: %s; Min acc balance:%s',
                 cls.CURRENCY, address, amount, cls.COIN_MANAGER.accumulation_min_balance)

        accumulation_address = wallet_transaction.external_accumulation_address or cls.COIN_MANAGER.get_accumulation_address(
            amount)

        # we want to process our tx faster
        gas_price = cls.COIN_MANAGER.gas_price_cache.get_increased_price()
        gas_amount = gas_price * cls.COIN_MANAGER.GAS_CURRENCY
        withdrawal_amount_wei = amount_wei - gas_amount
        withdrawal_amount = cls.COIN_MANAGER.get_amount_from_base_denomination(withdrawal_amount_wei)

        if cls.COIN_MANAGER.is_gas_price_reach_max_limit(gas_price):
            log.warning(f'Gas price too high: {gas_price}')
            cls.COIN_MANAGER.set_gas_price_too_high(wallet_transaction)
            return

        # in debug mode values can be very small
        if withdrawal_amount_wei <= 0:
            log.error(f'{cls.CURRENCY} withdrawal amount invalid: {withdrawal_amount}')
            wallet_transaction.set_balance_too_low()
            return

        # prepare tx
        wallet = cls.COIN_MANAGER.get_user_wallet(cls.CURRENCY.code, address)
        nonce = cls.COIN_MANAGER.client.eth.get_transaction_count(address)

        tx_hash = cls.COIN_MANAGER.send_tx(
            private_key=wallet.private_key,
            to_address=accumulation_address,
            amount=withdrawal_amount_wei,
            nonce=nonce,
            gasPrice=gas_price,
        )

        if not tx_hash:
            log.error('Unable to send accumulation TX')
            return

        AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=withdrawal_amount,
            tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=tx_hash.hex(),
        )
        wallet_transaction.set_accumulation_in_progress()

        AccumulationDetails.objects.create(
            currency=cls.CURRENCY,
            txid=tx_hash.hex(),
            from_address=address,
            to_address=accumulation_address
        )

        log.info('Accumulation TX %s sent from %s to %s', tx_hash.hex(), wallet.address, accumulation_address)

    @classmethod
    def accumulate_tokens(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address
        currency = wallet_transaction.currency

        gas_deposit_tx = accumulation_manager.get_last_gas_deposit_tx(wallet_transaction)
        if gas_deposit_tx is None:
            log.warning(f'Gas deposit for {address} not found or in process')
            return

        token = cls.COIN_MANAGER.get_token_by_symbol(currency)
        # amount checks
        token_amount = wallet_transaction.amount
        token_amount_wei = token.get_base_denomination_from_amount(token_amount)

        if token_amount <= to_decimal(0):
            log.warning('Cant accumulate %s from: %s; Balance too low: %s;',
                        currency, address, token_amount)
            return

        accumulation_address = wallet_transaction.external_accumulation_address or token.get_accumulation_address(
            token_amount)

        # we keep amount not as wei, it's more easy, so we need to convert it
        # checked_amount_wei = token.get_wei_from_amount(accumulation_state.current_balance)

        log.info(f'Accumulation {currency} from: {address}; Balance: {token_amount};')

        accumulation_gas_amount = cls.COIN_MANAGER.get_base_denomination_from_amount(gas_deposit_tx.amount)
        coin_amount_wei = cls.COIN_MANAGER.get_balance_in_base_denomination(address)

        if coin_amount_wei < accumulation_gas_amount:
            log.warning(f'Wallet {cls.CURRENCY} amount: {coin_amount_wei} less than gas needed '
                        f'{accumulation_gas_amount}, need to recheck')
            return

        accumulation_gas_required_amount = token.get_transfer_gas_amount(
            accumulation_address,
            token_amount_wei,
        )

        # calculate from existing wallet coin amount
        gas_price = int(accumulation_gas_amount / accumulation_gas_required_amount)

        wallet = cls.COIN_MANAGER.get_user_wallet(currency, address)
        nonce = cls.W3_CLIENT.eth.get_transaction_count(address)

        tx_hash = token.send_token(
            wallet.private_key,
            accumulation_address,
            token_amount_wei,
            gas=accumulation_gas_required_amount,
            gasPrice=gas_price,
            nonce=nonce
        )

        if not tx_hash:
            log.error('Unable to send token accumulation TX')
            return

        AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=token_amount,
            tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=tx_hash.hex(),
        )
        wallet_transaction.set_accumulation_in_progress()

        AccumulationDetails.objects.create(
            currency=cls.CURRENCY,
            token_currency=currency,
            txid=tx_hash.hex(),
            from_address=address,
            to_address=accumulation_address,
        )

        log.info('Token accumulation TX %s sent from %s to: %s',
                 tx_hash.hex(), wallet.address, accumulation_address)

    @classmethod
    def send_gas(cls, wallet_transaction_id, old_tx_data=None, old_tx_hash=None):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        old_tx_data = old_tx_data or {}

        if not old_tx_hash and not cls.is_gas_need(wallet_transaction):
            check_balance_task.apply_async(
                [cls.CURRENCY.code, wallet_transaction_id],
                queue=f'{cls.CURRENCY.code.lower()}_check_balances'
            )
            return

        address = wallet_transaction.wallet.address
        currency = wallet_transaction.currency
        token = cls.COIN_MANAGER.get_token_by_symbol(currency)

        token_amount_wei = token.get_base_denomination_balance(address)
        token_amount = token.get_amount_from_base_denomination(token_amount_wei)

        if to_decimal(token_amount) < to_decimal(token.accumulation_min_balance):
            log.warning('Current balance less than minimum, need to recheck')
            return

        # at this point we know amount is enough
        gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()
        gas_keeper_balance_wei = cls.COIN_MANAGER.get_balance_in_base_denomination(gas_keeper.address)
        accumulation_gas_amount = token.get_transfer_gas_amount(cls.SAFE_ADDR, token_amount_wei)
        gas_price = cls.COIN_MANAGER.gas_price_cache.get_increased_price(
            old_tx_data.get('gasPrice') or 0)

        if cls.COIN_MANAGER.is_gas_price_reach_max_limit(gas_price):
            log.warning(f'Gas price too high: {gas_price}')
            cls.COIN_MANAGER.set_gas_price_too_high(wallet_transaction)
            return

        accumulation_gas_total_amount = accumulation_gas_amount * gas_price

        if gas_keeper_balance_wei < accumulation_gas_total_amount:
            log.error('Gas keeper balance too low to send gas: %s',
                      cls.COIN_MANAGER.get_amount_from_base_denomination(gas_keeper_balance_wei))

        # prepare tx
        if old_tx_data:
            log.info('Gas transaction to %s will be replaced', Web3.to_checksum_address(address))
            tx_data = old_tx_data.copy()
            tx_data['gasPrice'] = gas_price
            tx_data['value'] = accumulation_gas_total_amount
            if cls.COIN_MANAGER.get_transaction_receipt(old_tx_hash):
                log.info('Gas TX %s sent. Do not need to replace.')
                return
        else:
            nonce = cls.COIN_MANAGER.wait_for_nonce(is_gas=True)
            tx_data = {
                'nonce': nonce,
                'gasPrice': gas_price,
                'gas': cls.COIN_MANAGER.GAS_CURRENCY,
                'from': Web3.to_checksum_address(gas_keeper.address),
                'to': address,
                'value': accumulation_gas_total_amount,
                'chainId': cls.CHAIN_ID,
            }
            log.info(tx_data)

        signed_tx = cls.W3_CLIENT.eth.account.sign_transaction(tx_data, gas_keeper.private_key)
        try:
            tx_hash = cls.W3_CLIENT.eth.send_raw_transaction(signed_tx.rawTransaction)
        except ValueError:
            log.exception('Unable to send accumulation TX')
            cls.COIN_MANAGER.release_nonce(is_gas=True)
            return

        if not tx_hash:
            log.error('Unable to send accumulation TX')
            cls.COIN_MANAGER.release_nonce(is_gas=True)
            return

        acc_transaction = AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=cls.COIN_MANAGER.get_amount_from_base_denomination(accumulation_gas_total_amount),
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=tx_hash.hex(),
        )
        wallet_transaction.set_waiting_for_gas()
        log.info('Gas deposit TX %s sent', tx_hash.hex())

        # wait tx processed
        try:
            cls.COIN_MANAGER.wait_for_transaction_receipt(tx_hash, poll_latency=3)
            acc_transaction.complete(is_gas=True)
            cls.COIN_MANAGER.release_nonce(is_gas=True)
            accumulate_tokens_task.apply_async([cls.CURRENCY.code, wallet_transaction_id])
        except RetryRequired:
            # retry with higher gas price
            cls.send_gas(wallet_transaction_id, old_tx_data=tx_data, old_tx_hash=tx_hash)

    @classmethod
    def _filter_transactions(cls, transactions, **kwargs) -> list:
        return transactions
