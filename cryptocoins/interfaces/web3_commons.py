import datetime
import logging
import time
from decimal import Decimal
from typing import Type, Union

from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from eth_abi.codec import ABICodec
from eth_abi.exceptions import NonEmptyPaddingBytes
from eth_abi.registry import registry
from web3 import Web3
from web3._utils.threads import Timeout
from web3.exceptions import TransactionNotFound

from core.models import FeesAndLimits
from cryptocoins.exceptions import RetryRequired
from cryptocoins.interfaces.common import BlockchainManager, GasPriceCache, Token, BlockchainTransaction

log = logging.getLogger(__name__)
abi_codec = ABICodec(registry)


class Web3Transaction(BlockchainTransaction):
    @classmethod
    def from_node(cls, tx_data):
        tx_hash = tx_data['hash']
        if hasattr(tx_hash, 'hex') and callable(getattr(tx_hash, 'hex')):
            tx_hash = tx_hash.hex()

        try:
            from_addr = Web3.toChecksumAddress(tx_data['from'])
        except:
            from_addr = tx_data['from']

        try:
            to_addr = Web3.toChecksumAddress(tx_data['to'])
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
            data_bytes = Web3.toBytes(hexstr=tx_data.input)
            if data_bytes[:4] != b'\xa9\x05\x9c\xbb':  # transfer fn
                return

            try:
                token_to_address, amount = abi_codec.decode_abi(['address', 'uint256'], data_bytes[4:])
            except NonEmptyPaddingBytes:
                return
            except Exception as e:
                log.exception('Cant parse transaction')
                return
            data.update({
                'to_addr': Web3.toChecksumAddress(token_to_address),
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
            data = Web3.toBytes(hexstr=data)
        return self.contract.decode_function_input(data)

    def send_token(self, private_key, to_address, amount_in_base_denomination, **kwargs):
        gas = kwargs['gas']
        gas_price = kwargs['gasPrice']
        nonce = kwargs['nonce']

        tx = self.contract.functions.transfer(
            to_address,
            amount_in_base_denomination,
        ).buildTransaction({
            'chainId': self.CHAIN_ID,
            'gas': gas,
            'gasPrice': gas_price,
            'nonce': nonce,
        })
        signed_tx = self.client.eth.account.signTransaction(tx, private_key)

        try:
            tx_hash = self.client.eth.sendRawTransaction(signed_tx.rawTransaction)
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

    def set_gas_price_too_high(self, wallet_transaction):
        wallet_transaction.state = wallet_transaction.STATE_GAS_PRICE_TOO_HIGH
        wallet_transaction.save(update_fields=['state', 'updated'])

    @property
    def accumulation_max_gas_price(self):
        limit = FeesAndLimits.get_limit(self.CURRENCY.code, FeesAndLimits.ACCUMULATION, FeesAndLimits.MAX_GAS_PRICE)
        return Web3.toWei(limit, 'gwei')

    def is_gas_price_reach_max_limit(self, price_wei):
        gas_price_limit = self.accumulation_max_gas_price
        return gas_price_limit and price_wei >= gas_price_limit

    def get_block(self, block_id):
        return self.client.eth.getBlock(block_id, full_transactions=True)

    def get_balance_in_base_denomination(self, address: str):
        return self.client.eth.getBalance(self.client.toChecksumAddress(address))

    def get_balance(self, address: str) -> Decimal:
        base_balance = self.get_balance_in_base_denomination(address)
        return self.get_amount_from_base_denomination(base_balance)

    def send_tx(self, private_key, to_address, amount, **kwargs):
        account = self.client.eth.account.from_key(private_key)
        signed_tx = self.client.eth.account.signTransaction({
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
            tx_hash = self.client.eth.sendRawTransaction(signed_tx.rawTransaction)
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
        return self.client.isAddress(address)

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
        nonce = self.client.eth.getTransactionCount(address)

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
                address_balance_wei = self.get_base_denomination_from_amount(address_balance)
                log.info(f'Accumulation {self.CURRENCY} dust from: {address}; Balance: {address_balance}')

                # we want to process our tx faster
                gas_price = self.gas_price_cache.get_price()
                gas_amount = gas_price * settings.ETH_TX_GAS  # TODO may be changed for non ETH currencies
                withdrawal_amount = address_balance_wei - gas_amount

                # in debug mode values can be very small
                if withdrawal_amount <= 0:
                    log.error(f'{self.CURRENCY} withdrawal amount invalid: '
                              f'{self.get_amount_from_base_denomination(withdrawal_amount)}')
                    return

                # prepare tx
                wallet = self.get_user_wallet(self.CURRENCY, address)
                nonce = self.client.eth.getTransactionCount(address)

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
