import datetime
import logging
from typing import List, Union

from django.conf import settings
from django.utils import timezone

from core.consts.currencies import ALL_TOKEN_CURRENCIES
from core.currency import Currency
from core.models.inouts.wallet import WalletTransactions
from cryptocoins.models import Keeper
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from lib.notifications import send_telegram_message

log = logging.getLogger(__name__)


class BaseMonitor:
    CURRENCY: Union[Currency, str]
    BLOCKCHAIN_CURRENCY: Union[Currency, str]
    SAFE_ADDRESS: str
    ACCUMULATION_TIMEOUT = 60 * 60
    DELTA_AMOUNT = 0
    OFFSET_SECONDS = 0

    def __init__(self):
        self.addresses_to_check = [self.SAFE_ADDRESS.lower()]
        keeper = Keeper.objects.filter(currency=self.BLOCKCHAIN_CURRENCY).first()
        if keeper:
            self.addresses_to_check.append(keeper.user_wallet.address.lower())

    def get_accumulation_transactions(self) -> List[AccumulationTransaction]:
        """
        Get wallet transactions queryset
        """
        accumulation_transactions = AccumulationTransaction.objects.filter(
            tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
            wallet_transaction__currency=self.CURRENCY,
            wallet_transaction__wallet__blockchain_currency=self.BLOCKCHAIN_CURRENCY,
            wallet_transaction__status=WalletTransactions.STATUS_NOT_SET,
            wallet_transaction__monitoring_state=WalletTransactions.MONITORING_STATE_NOT_CHECKED,
            wallet_transaction__state=WalletTransactions.STATE_ACCUMULATED,
        ).order_by('wallet_transaction', '-updated').distinct('wallet_transaction').prefetch_related(
            'wallet_transaction', 'wallet_transaction__wallet'
        )

        return accumulation_transactions

    def mark_wallet_transactions(self, notify=True):
        address_txs = {}
        accumulation_transactions = self.get_accumulation_transactions()
        for accumulation_transaction in accumulation_transactions:
            address = accumulation_transaction.wallet_transaction.wallet.address
            if address not in address_txs:
                outs_list = self.get_address_transactions(address)
                address_txs[address] = outs_list
            self.find_similar_accumulation(accumulation_transaction, address_txs[address], notify=notify)

    def get_alert_reason(self, address) -> str:
        # TODO split
        """
        Get alert reason
        """
        if self.CURRENCY in ALL_TOKEN_CURRENCIES:
            accumulation_transaction = AccumulationTransaction.objects.filter(
                wallet_transaction__wallet__address=address,
                wallet_transaction__wallet__currency=self.CURRENCY,
                wallet_transaction__wallet__blockchain_currency=self.BLOCKCHAIN_CURRENCY,
            ).order_by('-updated').first()

            if accumulation_transaction.tx_type == AccumulationTransaction.TX_TYPE_GAS_DEPOSIT:
                reason = f'Gas TX in pending\n{accumulation_transaction.tx_hash}'
            else:
                reason = f'Accumulation TX in pending\n{accumulation_transaction.tx_hash}'
            return reason
        else:
            accumulation_details = AccumulationDetails.objects.filter(
                from_address=address,
                currency=self.CURRENCY
            ).order_by('-created').first()

            if not accumulation_details:
                return 'Accumulation tx not found'

            if accumulation_details and accumulation_details.state == AccumulationDetails.STATE_PENDING:
                return f'Accumulation in pending\n{accumulation_details.txid}'

        return 'Unknown reason'

    def get_address_transactions(self, address, *args, **kwargs) -> List:
        """
        Get address transactions from third-party services like etherscan, blockstream etc
        """
        raise NotImplementedError

    def find_similar_accumulation(self, accumulation_transaction: AccumulationTransaction, address_txs, notify):
        """
        Try to find tx with identical amount as wallet transaction(deposit)
        """
        wallet_tx = accumulation_transaction.wallet_transaction
        timeout_datetime = wallet_tx.created + datetime.timedelta(seconds=self.ACCUMULATION_TIMEOUT)
        now = timezone.now()

        # filter txs by time and address
        accumulation_tx = None
        offset_time = wallet_tx.created - datetime.timedelta(seconds=self.OFFSET_SECONDS)

        for i, tx in enumerate(address_txs):
            if tx['created'] <= offset_time or timeout_datetime < tx['created']:
                continue
            if tx['hash'] == accumulation_transaction.tx_hash:
                accumulation_tx = tx
                break

        if not accumulation_tx:
            # timeout frame filled
            if now > timeout_datetime:
                wallet_tx.monitoring_state = WalletTransactions.MONITORING_STATE_NOT_ACCUMULATED
                wallet_tx.save(update_fields=['monitoring_state', 'updated'])

                if notify:
                    reason = self.get_alert_reason(wallet_tx.wallet.address)
                    msg = (f'{wallet_tx.amount} {wallet_tx.currency} was not accumulated!\n'
                           f'from {wallet_tx.wallet.address}\n'
                           f'{wallet_tx.tx_hash}\n'
                           f'{reason}\n')
                    send_telegram_message(msg, chat_id=settings.TELEGRAM_ALERTS_CHAT_ID)
            return

        # Accumulation to safe address
        if accumulation_tx['to'].lower() in self.addresses_to_check:
            if accumulation_tx['value'] == wallet_tx.amount:
                wallet_tx.monitoring_state = WalletTransactions.MONITORING_STATE_ACCUMULATED
            else:
                wallet_tx.monitoring_state = WalletTransactions.MONITORING_STATE_WRONG_AMOUNT
        # Accumulation to wrong address
        else:
            wallet_tx.monitoring_state = WalletTransactions.MONITORING_STATE_WRONG_ACCUMULATION
            msg = (f'{wallet_tx.currency.code} WRONG accumulation!\n'
                   f'from {accumulation_tx["from"]}\n'
                   f'to {accumulation_tx["to"]}\n'
                   f'{accumulation_tx["hash"]}')
            send_telegram_message(msg, chat_id=settings.TELEGRAM_ALERTS_CHAT_ID)
        wallet_tx.save(update_fields=['monitoring_state', 'updated'])
