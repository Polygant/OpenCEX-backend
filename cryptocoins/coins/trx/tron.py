import datetime
import logging
import time
from decimal import Decimal
from typing import Type
from typing import Union

from celery import group
from django.conf import settings
from django.utils import timezone
from tronpy import Tron
from tronpy import keys
from tronpy.abi import trx_abi
from tronpy.contract import Contract
from tronpy.exceptions import BlockNotFound
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider

from core.consts.currencies import TRC20_CURRENCIES
from core.currency import Currency
from core.models import WalletTransactions
from core.models.inouts.withdrawal import PENDING as WR_PENDING, FAILED_RESULTS
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee, get_min_accumulation_balance
from core.utils.withdrawal import get_withdrawal_requests_pending
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.coins.trx import TRX_CURRENCY
from cryptocoins.coins.trx.consts import TRC20_ABI
from cryptocoins.coins.trx.utils import is_valid_tron_address
from cryptocoins.evm.base import BaseEVMCoinHandler
from cryptocoins.evm.manager import register_evm_handler
from cryptocoins.interfaces.common import Token, BlockchainManager, BlockchainTransaction
from cryptocoins.models import AccumulationDetails
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from cryptocoins.tasks.evm import (
    check_tx_withdrawal_task,
    process_coin_deposit_task,
    process_tokens_deposit_task,
    accumulate_coin_task,
    accumulate_tokens_task,
)
from cryptocoins.utils.commons import (
    store_last_processed_block_id,
)
from exchange.settings import env
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal

log = logging.getLogger(__name__)

DEFAULT_BLOCK_ID_DELTA = 1000
TRX_SAFE_ADDR = settings.TRX_SAFE_ADDR
TRX_NET_FEE = settings.TRX_NET_FEE
TRC20_FEE_LIMIT = settings.TRC20_FEE_LIMIT

# tron_client = Tron(network='shasta')
tron_client = Tron(HTTPProvider(api_key=settings.TRONGRID_API_KEY))
# tron_client = Tron(HTTPProvider(endpoint_uri='http://52.53.189.99:8090'))
accumulation_manager = AccumulationManager()

class TrxTransaction(BlockchainTransaction):
    @classmethod
    def from_node(cls, tx_data):
        hash = tx_data['txID']
        data = tx_data['raw_data']
        contract_address = None
        to_address = None
        from_address = None
        amount = 0
        contract = data['contract'][0]
        if contract['type'] == 'TransferContract':
            value = contract['parameter']['value']
            amount = value['amount']
            from_address = value['owner_address']
            to_address = value['to_address']

        elif contract['type'] == 'TriggerSmartContract':
            value = contract['parameter']['value']
            contract_data = value.get('data')
            if contract_data:
                from_address = value['owner_address']
                contract_address = value['contract_address']
                if contract_data.startswith('a9059cbb'):
                    # hard replace padding bytes to zeroes for parsing
                    contract_fn_arguments = bytes.fromhex('00' * 12 + contract_data[32:])
                    try:
                        to_address, amount = trx_abi.decode(['address', 'uint256'], contract_fn_arguments)
                    except:
                        pass

        if hash and to_address:
            return cls({
                'hash': hash,
                'from_addr': from_address,
                'to_addr': to_address,
                'value': amount,
                'contract_address': contract_address,
                'is_success': tx_data['ret'][0]['contractRet'] == 'SUCCESS',
            })


class TRC20Token(Token):
    ABI = TRC20_ABI
    BLOCKCHAIN_CURRENCY: Currency = TRX_CURRENCY
    DEFAULT_TRANSFER_GAS_LIMIT: int = 1_000_000
    DEFAULT_TRANSFER_GAS_MULTIPLIER: int = 1

    def get_contract(self):
        """Get a contract object."""
        cntr = Contract(
            addr=keys.to_base58check_address(self.params.contract_address),
            bytecode='',
            name='',
            abi=TRC20_ABI,
            origin_energy_limit=self.params.origin_energy_limit or 0,
            user_resource_percent=self.params.consume_user_resource_percent or 100,
            client=tron_client,
        )
        return cntr

    def send_token(self, private_key, to_address, amount, **kwargs):
        if isinstance(private_key, bytes):
            private_key = PrivateKey(private_key)
        elif isinstance(private_key, str):
            private_key = PrivateKey(bytes.fromhex(private_key))

        from_address = private_key.public_key.to_base58check_address()

        txn = (
            self.contract.functions.transfer(to_address, amount)
                .with_owner(from_address)  # address of the private key
                .fee_limit(settings.TRC20_FEE_LIMIT)
                .build()
                .sign(private_key)
        )
        return txn.broadcast()

    def get_base_denomination_balance(self, address: str) -> int:
        return self.contract.functions.balanceOf(address)


class TronManager(BlockchainManager):
    CURRENCY: Currency = TRX_CURRENCY
    GAS_CURRENCY = settings.TRX_NET_FEE
    TOKEN_CURRENCIES = TRC20_CURRENCIES
    TOKEN_CLASS: Type[Token] = TRC20Token
    BASE_DENOMINATION_DECIMALS: int = 6
    MIN_BALANCE_TO_ACCUMULATE_DUST = Decimal('4')
    COLD_WALLET_ADDRESS = settings.TRX_SAFE_ADDR

    def get_latest_block_num(self):
        return self.client.get_latest_block_number()

    def get_block(self, block_id):
        return self.client.get_block(block_id)

    def get_balance_in_base_denomination(self, address: str):
        return self.get_base_denomination_from_amount(self.get_balance(address))

    def get_balance(self, address: str) -> Decimal:
        return self.client.get_account_balance(address)

    def is_valid_address(self, address: str) -> bool:
        return is_valid_tron_address(address)

    def send_tx(self, private_key: Union[bytes, PrivateKey, str], to_address, amount, **kwargs):
        if isinstance(private_key, bytes):
            private_key = PrivateKey(private_key)
        elif isinstance(private_key, str):
            private_key = PrivateKey(bytes.fromhex(private_key))

        from_address = private_key.public_key.to_base58check_address()

        txn = (
            tron_client.trx.transfer(from_address, to_address, amount)
                .memo("")
                .build()
                .sign(private_key)
        )
        return txn.broadcast()

    def accumulate_dust(self):
        to_address = self.get_gas_keeper_wallet().address

        from_addresses = self.get_currency_and_addresses_for_accumulation_dust()

        for address, currency in from_addresses:
            address_balance = self.get_balance(address)
            if address_balance >= self.MIN_BALANCE_TO_ACCUMULATE_DUST:
                amount_sun = self.get_base_denomination_from_amount(address_balance)
                log.info(f'Accumulation {self.CURRENCY} dust from: {address}; Balance: {address_balance}')

                withdrawal_amount = amount_sun - self.GAS_CURRENCY

                # in debug mode values can be very small
                if withdrawal_amount <= 0:
                    log.error(f'{currency} withdrawal amount invalid: '
                              f'{self.get_amount_from_base_denomination(withdrawal_amount)}')
                    return

                # prepare tx
                wallet = self.get_user_wallet(currency, address)
                res = tron_manager.send_tx(wallet.private_key, to_address, withdrawal_amount)
                tx_hash = res.get('txid')

                if not tx_hash:
                    log.error('Unable to send dust accumulation TX')
                    return

                log.info(f'Accumulation TX {tx_hash} sent from {address} to {to_address}')


tron_manager = TronManager(tron_client)


@register_evm_handler
class TronHandler(BaseEVMCoinHandler):
    CURRENCY = TRX_CURRENCY
    GAS_CURRENCY = settings.TRX_NET_FEE
    COIN_MANAGER = tron_manager
    TOKEN_CURRENCIES = tron_manager.registered_token_currencies
    TOKEN_CONTRACT_ADDRESSES = tron_manager.registered_token_addresses
    TRANSACTION_CLASS = TrxTransaction
    SAFE_ADDR = settings.TRX_SAFE_ADDR
    BLOCK_GENERATION_TIME = settings.TRX_BLOCK_GENERATION_TIME
    ACCUMULATION_PERIOD = settings.TRX_TRC20_ACCUMULATION_PERIOD
    IS_ENABLED = env('COMMON_TASKS_TRON', default=True)

    @classmethod
    def process_block(cls, block_id):
        started_at = time.time()
        time.sleep(0.1)
        log.info('Processing block #%s', block_id)

        try:
            block = cls.COIN_MANAGER.get_block(block_id)
        except BlockNotFound:
            log.warning(f'Block not found: {block_id}')
            return
        except Exception as e:
            store_last_processed_block_id(currency=cls.CURRENCY, block_id=block_id - 1)
            raise e

        transactions = block.get('transactions', [])

        if not transactions:
            log.info('Block #%s has no transactions, skipping', block_id)
            return

        log.info('Transactions count in block #%s: %s', block_id, len(transactions))

        coin_deposit_jobs = []
        tokens_deposit_jobs = []

        coin_withdrawal_requests_pending = get_withdrawal_requests_pending([cls.CURRENCY])
        tokens_withdrawal_requests_pending = get_withdrawal_requests_pending(
            cls.TOKEN_CURRENCIES, blockchain_currency=cls.CURRENCY.code)

        coin_withdrawal_requests_pending_txs = [i.txid for i in coin_withdrawal_requests_pending]
        tokens_withdrawal_requests_pending_txs = [i.txid for i in tokens_withdrawal_requests_pending]

        check_coin_withdrawal_jobs = []
        check_tokens_withdrawal_jobs = []

        all_valid_transactions = []
        all_transactions = []

        for tx_data in transactions:
            tx: TrxTransaction = TrxTransaction.from_node(tx_data)
            if not tx:
                continue
            if tx.is_success:
                all_valid_transactions.append(tx)
            all_transactions.append(tx)

        # Withdrawals
        for tx in all_transactions:
            # is TRX withdrawal request tx?
            if tx.hash in coin_withdrawal_requests_pending_txs:
                check_coin_withdrawal_jobs.append(check_tx_withdrawal_task.s(cls.CURRENCY.code, None, tx.as_dict()))
                continue

            # is TRC20 withdrawal request tx?
            if tx.hash in tokens_withdrawal_requests_pending_txs:
                check_tokens_withdrawal_jobs.append(check_tx_withdrawal_task.s(cls.CURRENCY.code, None, tx.as_dict()))
                continue

        keeper_wallet = cls.COIN_MANAGER.get_keeper_wallet()
        gas_keeper_wallet = cls.COIN_MANAGER.get_keeper_wallet()
        trx_addresses = set(cls.COIN_MANAGER.get_user_addresses())

        trx_addresses_deps = set(trx_addresses)
        trx_addresses_deps.add(TRX_SAFE_ADDR)

        # Deposits
        for tx in all_valid_transactions:
            # process TRX deposit

            if tx.to_addr in trx_addresses_deps:
                # Process TRX
                if not tx.contract_address:
                    coin_deposit_jobs.append(process_coin_deposit_task.s(cls.CURRENCY.code, tx.as_dict()))
                # Process TRC20
                elif tx.contract_address and tx.contract_address in cls.TOKEN_CONTRACT_ADDRESSES:
                    tokens_deposit_jobs.append(process_tokens_deposit_task.s(cls.CURRENCY.code, tx.as_dict()))

        # Accumulations monitoring
        for tx in all_valid_transactions:
            if tx.from_addr in trx_addresses and tx.to_addr not in trx_addresses:

                # skip keepers withdrawals
                if tx.from_addr in [keeper_wallet.address, gas_keeper_wallet.address]:
                    continue

                accumulation_details = AccumulationDetails.objects.filter(
                    txid=tx.hash
                ).first()

                if accumulation_details:
                    log.info(f'Accumulation details for {tx.hash} already exists')
                    continue

                accumulation_details = {
                    'currency': TRX_CURRENCY,
                    'txid': tx.hash,
                    'from_address': tx.from_addr,
                    'to_address': tx.to_addr,
                    'state': AccumulationDetails.STATE_COMPLETED
                }

                if not tx.contract_address:
                    # Store TRX accumulations
                    AccumulationDetails.objects.create(**accumulation_details)

                elif tx.contract_address and tx.contract_address in cls.TOKEN_CONTRACT_ADDRESSES:
                    # Store TRC20 accumulations
                    token = cls.COIN_MANAGER.get_token_by_address(tx.contract_address)
                    accumulation_details['token_currency'] = token.currency
                    AccumulationDetails.objects.create(**accumulation_details)

        if coin_deposit_jobs:
            log.info('Need to check TRX deposits count: %s', len(coin_deposit_jobs))
            group(coin_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_deposits')

        if tokens_deposit_jobs:
            log.info('Need to check TRC20 withdrawals count: %s', len(tokens_deposit_jobs))
            group(tokens_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_deposits')

        if check_coin_withdrawal_jobs:
            log.info('Need to check TRX withdrawals count: %s', len(check_coin_withdrawal_jobs))
            group(check_coin_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        if check_tokens_withdrawal_jobs:
            log.info('Need to check TRC20 withdrawals count: %s', len(check_coin_withdrawal_jobs))
            group(check_tokens_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        execution_time = time.time() - started_at
        log.info('Block #%s processed in %.2f sec. (TRX TX count: %s, TRC20 TX count: %s, WR TX count: %s)',
                 block_id, execution_time, len(coin_deposit_jobs), len(tokens_deposit_jobs),
                 len(check_tokens_withdrawal_jobs) + len(check_coin_withdrawal_jobs))

    @classmethod
    def check_tx_withdrawal(cls, withdrawal_id, tx_data):
        tx = TrxTransaction(tx_data)
        withdrawal_request = WithdrawalRequest.objects.filter(
            txid=tx.hash,
            state=WR_PENDING,
        ).first()

        if withdrawal_request is None:
            log.warning('Invalid withdrawal request state for TX %s', tx.hash)
            return

        if tx.is_success:
            withdrawal_request.complete()
        else:
            withdrawal_request.fail()

    @classmethod
    def process_coin_deposit(cls, tx_data: dict):
        """
        Process TRX deposit, excepting inner gas deposits, etc
        """
        log.info('Processing trx deposit: %s', tx_data)
        tx = cls.TRANSACTION_CLASS(tx_data)
        amount = cls.COIN_MANAGER.get_amount_from_base_denomination(tx.value)

        trx_keeper = cls.COIN_MANAGER.get_keeper_wallet()
        external_accumulation_addresses = accumulation_manager.get_external_accumulation_addresses([TRX_CURRENCY])

        # is accumulation tx?
        if tx.to_addr in [TRX_SAFE_ADDR, trx_keeper.address] + external_accumulation_addresses:
            accumulation_transaction = AccumulationTransaction.objects.filter(
                tx_hash=tx.hash,
            ).first()

            if accumulation_transaction is None:
                log.error(f'Accumulation TX {tx.hash} not exist')
                return

            if accumulation_transaction.tx_state == AccumulationTransaction.STATE_COMPLETED:
                log.info(f'Accumulation TX {tx.hash} already processed')
                return

            accumulation_transaction.complete()

            log.info(f'Tx {tx.hash} is TRX accumulation')
            return

        trx_gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()
        # is inner gas deposit?
        if tx.from_addr == trx_gas_keeper.address:
            accumulation_transaction = AccumulationTransaction.objects.filter(
                tx_hash=tx.hash,
                tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            ).first()

            if accumulation_transaction is None:
                log.error(f'Gas accumulation TX {tx.hash} not found')
                return

            if accumulation_transaction.tx_state == AccumulationTransaction.STATE_COMPLETED:
                log.info(f'Accumulation TX {tx.hash} already processed as token gas')
                return

            log.info(f'Tx {tx.hash} is gas deposit')
            accumulation_transaction.complete(is_gas=True)
            accumulate_tokens_task.apply_async(
                [cls.CURRENCY.code, accumulation_transaction.wallet_transaction_id],
                queue='trx_accumulations',
            )
            return

        db_wallet = cls.COIN_MANAGER.get_wallet_db_instance(TRX_CURRENCY, tx.to_addr)
        if db_wallet is None:
            log.error(f'Wallet TRX {tx.to_addr} not exists or blocked')
            return

        # is already processed?
        db_wallet_transaction = WalletTransactions.objects.filter(
            tx_hash__iexact=tx.hash,
            wallet_id=db_wallet.id,
        ).first()

        if db_wallet_transaction is not None:
            log.warning('TX %s already processed as TRX deposit', tx.hash)
            return

        # make deposit
        # check for keeper deposit
        if db_wallet.address == trx_keeper.address:
            log.info('TX %s is keeper TRX deposit: %s', tx.hash, amount)
            return

        # check for gas keeper deposit
        if db_wallet.address == trx_gas_keeper.address:
            log.info('TX %s is gas keeper TRX deposit: %s', tx.hash, amount)
            return

        # check for accumulation min limit
        if amount < cls.COIN_MANAGER.accumulation_min_balance:
            log.info(
                'TX %s amount: %s less accumulation min limit: %s',
                tx.hash, amount, cls.COIN_MANAGER.accumulation_min_balance
            )
            return

        WalletTransactions.objects.create(
            wallet=db_wallet,
            tx_hash=tx.hash,
            amount=amount,
            currency=TRX_CURRENCY,
        )
        log.info('TX %s processed as %s TRX deposit', tx.hash, amount)

    @classmethod
    def process_tokens_deposit(cls, tx_data: dict):
        """
        Process TRC20 deposit
        """
        log.info('Processing TRC20 deposit: %s', tx_data)
        tx = TrxTransaction(tx_data)

        token = cls.COIN_MANAGER.get_token_by_address(tx.contract_address)
        token_to_addr = tx.to_addr
        token_amount = token.get_amount_from_base_denomination(tx.value)
        trx_keeper = cls.COIN_MANAGER.get_keeper_wallet()
        external_accumulation_addresses = accumulation_manager.get_external_accumulation_addresses(
            list(cls.TOKEN_CURRENCIES)
        )

        if token_to_addr in [TRX_SAFE_ADDR, trx_keeper.address] + external_accumulation_addresses:
            log.info(f'TX {tx.hash} is {token_amount} {token.currency} accumulation')

            accumulation_transaction = AccumulationTransaction.objects.filter(
                tx_hash=tx.hash,
            ).first()
            if accumulation_transaction is None:
                # accumulation from outside
                log.error('Token accumulation TX %s not exist', tx.hash)
                return

            accumulation_transaction.complete()
            return

        db_wallet = cls.COIN_MANAGER.get_wallet_db_instance(token.currency, token_to_addr)
        if db_wallet is None:
            log.error('Wallet %s %s not exists or blocked', token.currency, token_to_addr)
            return

        db_wallet_transaction = WalletTransactions.objects.filter(
            tx_hash__iexact=tx.hash,
            wallet_id=db_wallet.id,
        ).first()
        if db_wallet_transaction is not None:
            log.warning(f'TX {tx.hash} already processed as {token.currency} deposit')
            return

        # check for keeper deposit
        if db_wallet.address == trx_keeper.address:
            log.info(f'TX {tx.hash} is keeper {token.currency} deposit: {token_amount}')
            return

        # check for gas keeper deposit
        trx_gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()
        if db_wallet.address == trx_gas_keeper.address:
            log.info(f'TX {tx.hash} is keeper {token.currency} deposit: {token_amount}')
            return

        # check for accumulation min limit
        if token_amount < get_min_accumulation_balance(db_wallet.currency):
            log.info(
                'TX %s amount: %s less accumulation min limit: %s',
                tx.hash, token_amount, cls.COIN_MANAGER.accumulation_min_balance
            )
            return

        WalletTransactions.objects.create(
            wallet_id=db_wallet.id,
            tx_hash=tx.hash,
            amount=token_amount,
            currency=token.currency,
        )

        log.info(f'TX {tx.hash} processed as {token_amount} {token.currency} deposit')

    @classmethod
    def withdraw_coin(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        address = withdrawal_request.data.get('destination')
        keeper = cls.COIN_MANAGER.get_keeper_wallet()
        amount_sun = cls.COIN_MANAGER.get_base_denomination_from_amount(withdrawal_request.amount)

        withdrawal_fee_sun = cls.COIN_MANAGER.get_base_denomination_from_amount(
            to_decimal(get_withdrawal_fee(TRX_CURRENCY, TRX_CURRENCY)))
        amount_to_send_sun = amount_sun - withdrawal_fee_sun

        # todo: check min limit
        if amount_to_send_sun <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        if amount_to_send_sun - cls.GAS_CURRENCY < 0:
            log.error('Keeper balance too low')
            return

        private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

        res = cls.COIN_MANAGER.send_tx(private_key, address, amount_to_send_sun)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send withdrawal TX')

        receipt = res.wait()

        if (
                "receipt" in receipt
                and "result" in receipt["receipt"]
                and receipt["receipt"]["result"] in FAILED_RESULTS
        ):
            withdrawal_request.fail()
            log.error('Failed - %s', receipt['receipt']['result'])
        else:
            withdrawal_request.state = WR_PENDING
            withdrawal_request.txid = txid
            withdrawal_request.our_fee_amount = cls.COIN_MANAGER.get_amount_from_base_denomination(withdrawal_fee_sun)
            withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])

        log.info(receipt)
        log.info('TRX withdrawal TX %s sent', txid)


    @classmethod
    def withdraw_tokens(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        address = withdrawal_request.data.get('destination')
        currency = withdrawal_request.currency

        token = cls.COIN_MANAGER.get_token_by_symbol(currency)
        send_amount_sun = token.get_base_denomination_from_amount(withdrawal_request.amount)
        withdrawal_fee_sun = token.get_base_denomination_from_amount(token.withdrawal_fee)
        amount_to_send_sun = send_amount_sun - withdrawal_fee_sun

        if amount_to_send_sun <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        keeper = cls.COIN_MANAGER.get_keeper_wallet()
        keeper_trx_balance = cls.COIN_MANAGER.get_balance_in_base_denomination(keeper.address)
        keeper_token_balance = token.get_base_denomination_balance(keeper.address)

        if keeper_trx_balance < cls.GAS_CURRENCY:
            log.warning('Keeper not enough TRX, skipping')
            return

        if keeper_token_balance < amount_to_send_sun:
            log.warning('Keeper not enough %s, skipping', currency)
            return

        private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

        res = token.send_token(private_key, address, amount_to_send_sun)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send TRX TX')

        receipt = res.wait()

        if (
                "receipt" in receipt
                and "result" in receipt["receipt"]
                and receipt["receipt"]["result"] in FAILED_RESULTS
        ):
            withdrawal_request.fail()
            log.error('Failed - %s', receipt['receipt']['result'])
        else:
            withdrawal_request.state = WR_PENDING
            withdrawal_request.txid = txid
            withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(withdrawal_fee_sun)
            withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])

        log.info(receipt)
        log.info('%s withdrawal TX %s sent', currency, txid)


    @classmethod
    def check_balance(cls, wallet_transaction_id):
        """Splits blockchain currency accumulation and token accumulation"""
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        currency = wallet_transaction.currency

        # TRX
        if currency == TRX_CURRENCY:
            wallet_transaction.set_ready_for_accumulation()
            accumulate_coin_task.apply_async(
                [cls.CURRENCY.code, wallet_transaction_id],
                queue=f'{cls.CURRENCY.code.lower()}_accumulations'
            )
        # tokens
        else:
            wallet_transaction.set_ready_for_accumulation()
            accumulate_tokens_task.apply_async(
                [cls.CURRENCY.code, wallet_transaction_id],
                queue=f'{cls.CURRENCY.code.lower()}_tokens_accumulations'
            )

    @classmethod
    def accumulate_coin(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address

        amount = wallet_transaction.amount
        amount_sun = cls.COIN_MANAGER.get_base_denomination_from_amount(amount)

        log.info('Accumulation TRX from: %s; Balance: %s; Min acc balance:%s',
                 address, amount, cls.COIN_MANAGER.accumulation_min_balance)

        # minus coins to be burnt
        withdrawal_amount = amount_sun - cls.GAS_CURRENCY

        # in debug mode values can be very small
        if withdrawal_amount <= 0:
            log.error(f'TRX withdrawal amount invalid: {withdrawal_amount}')
            wallet_transaction.set_balance_too_low()
            return

        accumulation_address = wallet_transaction.external_accumulation_address or cls.COIN_MANAGER.get_accumulation_address(
            amount)

        # prepare tx
        wallet = cls.COIN_MANAGER.get_user_wallet('TRX', address)

        res = cls.COIN_MANAGER.send_tx(wallet.private_key, accumulation_address, withdrawal_amount)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send withdrawal TX')

        AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=cls.COIN_MANAGER.get_amount_from_base_denomination(withdrawal_amount),
            tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=txid,
        )
        wallet_transaction.set_accumulation_in_progress()
        # AccumulationDetails.objects.create(
        #     currency=TRX_CURRENCY,
        #     txid=txid,
        #     from_address=address,
        #     to_address=accumulation_address
        # )

        reciept = res.wait()
        log.info(reciept)
        log.info(f'Accumulation TX {txid} sent from {wallet.address} to {accumulation_address}')

    @classmethod
    def accumulate_tokens(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address
        currency = wallet_transaction.currency

        token = cls.COIN_MANAGER.get_token_by_symbol(currency)
        token_amount = wallet_transaction.amount
        token_amount_sun = token.get_base_denomination_from_amount(token_amount)

        log.info(f'Accumulation {currency} from: {address}; Balance: {token_amount};')

        accumulation_address = wallet_transaction.external_accumulation_address or token.get_accumulation_address(
            token_amount)

        gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()

        # send trx from gas keeper to send tokens
        log.info('Trying to send token fee from GasKeeper')
        res = cls.COIN_MANAGER.send_tx(gas_keeper.private_key, address, TRC20_FEE_LIMIT)
        gas_txid = res.get('txid')

        if not res.get('result') or not gas_txid:
            log.error('Unable to send fee TX')

        acc_transaction = AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=cls.COIN_MANAGER.get_amount_from_base_denomination(TRC20_FEE_LIMIT),
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=gas_txid,
        )
        wallet_transaction.set_waiting_for_gas()

        receipt = res.wait()
        log.info(receipt)

        acc_transaction.complete(is_gas=True)

        wallet = cls.COIN_MANAGER.get_user_wallet(currency, address)
        res = token.send_token(wallet.private_key, accumulation_address, token_amount_sun)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send withdrawal token TX')

        AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=token.get_amount_from_base_denomination(token_amount_sun),
            tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=txid,
        )
        wallet_transaction.set_accumulation_in_progress()

        receipt = res.wait()
        log.info(receipt)
        log.info('Token accumulation TX %s sent from %s to: %s', txid, wallet.address, accumulation_address)
