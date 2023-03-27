import logging
from decimal import Decimal
from typing import Type
from typing import Union

from django.conf import settings
from tronpy import Tron
from tronpy import keys
from tronpy.abi import trx_abi
from tronpy.contract import Contract
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider

from core.consts.currencies import TRC20_CURRENCIES
from core.currency import Currency
from cryptocoins.coins.trx import TRX_CURRENCY
from cryptocoins.coins.trx.consts import TRC20_ABI
from cryptocoins.coins.trx.utils import is_valid_tron_address
from cryptocoins.interfaces.common import Token, BlockchainManager, BlockchainTransaction
from django.utils import timezone
import datetime

log = logging.getLogger(__name__)

# tron_client = Tron(network='shasta')
tron_client = Tron(HTTPProvider(api_key=settings.TRONGRID_API_KEY))
# tron_client = Tron(HTTPProvider(endpoint_uri='http://52.53.189.99:8090'))


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
