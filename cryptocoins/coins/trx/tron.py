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
from core.models.inouts.withdrawal import PENDING as WR_PENDING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee
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
                        to_address, amount = trx_abi.decode_abi(['address', 'uint256'], contract_fn_arguments)
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
        from core.models import WalletTransactions

        to_address = self.get_gas_keeper_wallet().address

        addresses = WalletTransactions.objects.filter(
            currency__in=self.registered_token_currencies,
            wallet__blockchain_currency=self.CURRENCY.code,
            created__gt=timezone.now() - datetime.timedelta(days=1),

        ).values_list('wallet__address', flat=True).distinct()

        for address in addresses:
            address_balance = self.get_balance(address)
            if address_balance >= self.MIN_BALANCE_TO_ACCUMULATE_DUST:
                amount_sun = self.get_base_denomination_from_amount(address_balance)
                log.info(f'Accumulation {self.CURRENCY} dust from: {address}; Balance: {address_balance}')

                withdrawal_amount = amount_sun - settings.TRX_NET_FEE

                # in debug mode values can be very small
                if withdrawal_amount <= 0:
                    log.error(f'{self.CURRENCY} withdrawal amount invalid: '
                              f'{self.get_amount_from_base_denomination(withdrawal_amount)}')
                    return

                # prepare tx
                wallet = self.get_user_wallet(self.CURRENCY, address)
                res = tron_manager.send_tx(wallet.private_key, to_address, withdrawal_amount)
                tx_hash = res.get('txid')

                if not tx_hash:
                    log.error('Unable to send dust accumulation TX')
                    return

                log.info(f'Accumulation TX {tx_hash.hex()} sent from {address} to {to_address}')


tron_manager = TronManager(tron_client)


@register_evm_handler
class TronHandler(BaseEVMCoinHandler):
    CURRENCY = TRX_CURRENCY
    COIN_MANAGER = tron_manager
    TOKEN_CURRENCIES = tron_manager.registered_token_currencies
    TOKEN_CONTRACT_ADDRESSES = tron_manager.registered_token_addresses
    TRANSACTION_CLASS = TrxTransaction
    SAFE_ADDR = settings.TRX_SAFE_ADDR

    @classmethod
    def process_block(cls, block_id):
        started_at = time.time()
        time.sleep(0.1)
        log.info('Processing block #%s', block_id)

        try:
            block = tron_manager.get_block(block_id)
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

        keeper_wallet = tron_manager.get_keeper_wallet()
        gas_keeper_wallet = tron_manager.get_keeper_wallet()
        trx_addresses = set(tron_manager.get_user_addresses())

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
                    token = tron_manager.get_token_by_address(tx.contract_address)
                    accumulation_details['token_currency'] = token.currency
                    AccumulationDetails.objects.create(**accumulation_details)

        if coin_deposit_jobs:
            log.info('Need to check TRX deposits count: %s', len(coin_deposit_jobs))
            group(coin_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code}_deposits')

        if tokens_deposit_jobs:
            log.info('Need to check TRC20 withdrawals count: %s', len(tokens_deposit_jobs))
            group(tokens_deposit_jobs).apply_async(queue=f'{cls.CURRENCY.code}_deposits')

        if check_coin_withdrawal_jobs:
            log.info('Need to check TRX withdrawals count: %s', len(check_coin_withdrawal_jobs))
            group(check_coin_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code}_check_balances')

        if check_tokens_withdrawal_jobs:
            log.info('Need to check TRC20 withdrawals count: %s', len(check_coin_withdrawal_jobs))
            group(check_tokens_withdrawal_jobs).apply_async(queue=f'{cls.CURRENCY.code}_check_balances')

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
    def withdraw_trx(cls, withdrawal_request_id, password):
        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        address = withdrawal_request.data.get('destination')
        keeper = tron_manager.get_keeper_wallet()
        amount_sun = tron_manager.get_base_denomination_from_amount(withdrawal_request.amount)

        withdrawal_fee_sun = tron_manager.get_base_denomination_from_amount(
            to_decimal(get_withdrawal_fee(TRX_CURRENCY, TRX_CURRENCY)))
        amount_to_send_sun = amount_sun - withdrawal_fee_sun

        # todo: check min limit
        if amount_to_send_sun <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        if amount_to_send_sun - TRX_NET_FEE < 0:
            log.error('Keeper balance too low')
            return

        private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

        res = tron_manager.send_tx(private_key, address, amount_to_send_sun)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send withdrawal TX')

        withdrawal_request.state = WR_PENDING
        withdrawal_request.txid = txid
        withdrawal_request.our_fee_amount = tron_manager.get_amount_from_base_denomination(withdrawal_fee_sun)
        withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])
        receipt = res.wait()
        log.info(receipt)
        log.info('TRX withdrawal TX %s sent', txid)

    @classmethod
    def withdraw_trc20(cls, withdrawal_request_id, password):
        withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

        address = withdrawal_request.data.get('destination')
        currency = withdrawal_request.currency

        token = tron_manager.get_token_by_symbol(currency)
        send_amount_sun = token.get_base_denomination_from_amount(withdrawal_request.amount)
        withdrawal_fee_sun = token.get_base_denomination_from_amount(token.withdrawal_fee)
        amount_to_send_sun = send_amount_sun - withdrawal_fee_sun

        if amount_to_send_sun <= 0:
            log.error('Invalid withdrawal amount')
            withdrawal_request.fail()
            return

        keeper = tron_manager.get_keeper_wallet()
        keeper_trx_balance = tron_manager.get_balance_in_base_denomination(keeper.address)
        keeper_token_balance = token.get_base_denomination_balance(keeper.address)

        if keeper_trx_balance < TRX_NET_FEE:
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

        withdrawal_request.state = WR_PENDING
        withdrawal_request.txid = txid
        withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(withdrawal_fee_sun)
        withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])
        receipt = res.wait()
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
                queue=f'{cls.CURRENCY.code}_accumulations'
            )
        # tokens
        else:
            wallet_transaction.set_ready_for_accumulation()
            accumulate_tokens_task.apply_async(
                [cls.CURRENCY.code, wallet_transaction_id],
                queue=f'{cls.CURRENCY.code}_tokens_accumulations'
            )

    @classmethod
    def accumulate_trx(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address

        amount = wallet_transaction.amount
        amount_sun = tron_manager.get_base_denomination_from_amount(amount)

        log.info('Accumulation TRX from: %s; Balance: %s; Min acc balance:%s',
                 address, amount, tron_manager.accumulation_min_balance)

        # minus coins to be burnt
        withdrawal_amount = amount_sun - TRX_NET_FEE

        # in debug mode values can be very small
        if withdrawal_amount <= 0:
            log.error(f'TRX withdrawal amount invalid: {withdrawal_amount}')
            wallet_transaction.set_balance_too_low()
            return

        accumulation_address = wallet_transaction.external_accumulation_address or tron_manager.get_accumulation_address(
            amount)

        # prepare tx
        wallet = tron_manager.get_user_wallet('TRX', address)

        res = tron_manager.send_tx(wallet.private_key, accumulation_address, withdrawal_amount)
        txid = res.get('txid')

        if not res.get('result') or not txid:
            log.error('Unable to send withdrawal TX')

        AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=tron_manager.get_amount_from_base_denomination(withdrawal_amount),
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
    def accumulate_trc20(cls, wallet_transaction_id):
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        address = wallet_transaction.wallet.address
        currency = wallet_transaction.currency

        token = tron_manager.get_token_by_symbol(currency)
        token_amount = wallet_transaction.amount
        token_amount_sun = token.get_base_denomination_from_amount(token_amount)

        log.info(f'Accumulation {currency} from: {address}; Balance: {token_amount};')

        accumulation_address = wallet_transaction.external_accumulation_address or token.get_accumulation_address(
            token_amount)

        gas_keeper = tron_manager.get_gas_keeper_wallet()

        # send trx from gas keeper to send tokens
        log.info('Trying to send token fee from GasKeeper')
        res = tron_manager.send_tx(gas_keeper.private_key, address, TRC20_FEE_LIMIT)
        gas_txid = res.get('txid')

        if not res.get('result') or not gas_txid:
            log.error('Unable to send fee TX')

        acc_transaction = AccumulationTransaction.objects.create(
            wallet_transaction=wallet_transaction,
            amount=tron_manager.get_amount_from_base_denomination(TRC20_FEE_LIMIT),
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            tx_state=AccumulationTransaction.STATE_PENDING,
            tx_hash=gas_txid,
        )
        wallet_transaction.set_waiting_for_gas()

        receipt = res.wait()
        log.info(receipt)

        acc_transaction.complete(is_gas=True)

        wallet = tron_manager.get_user_wallet(currency, address)
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
