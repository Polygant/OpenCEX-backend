import datetime
import logging
from typing import List, Union

from django.utils import timezone

from core.consts.currencies import ERC20_CURRENCIES
from core.currency import Currency
from core.models.inouts.wallet import WalletTransactions
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.models.accumulation_transaction import AccumulationTransaction

log = logging.getLogger(__name__)


class BaseMonitor:
    CURRENCY: Union[Currency, str]
    BLOCKCHAIN_CURRENCY: Union[Currency, str]
    SAFE_ADDRESS: str
    ACCUMULATION_TIMEOUT = 60 * 60
    DELTA_AMOUNT = 0
    OFFSET_SECONDS = 0

    def get_wallet_transactions(self) -> List[WalletTransactions]:
        """
        Get wallet transactions queryset
        """
        wallet_transactions_qs = WalletTransactions.objects.filter(
            status=WalletTransactions.STATUS_NOT_SET,
            state=WalletTransactions.STATE_NOT_CHECKED,
            currency=self.CURRENCY,
            wallet__blockchain_currency=self.BLOCKCHAIN_CURRENCY
        ).order_by('created')

        return wallet_transactions_qs

    def mark_wallet_transactions(self):
        address_txs = {}
        wallet_transactions_qs = self.get_wallet_transactions()
        for wallet_tx in wallet_transactions_qs:
            if wallet_tx.wallet.address not in address_txs:
                outs_list = self.get_address_transactions(wallet_tx.wallet.address)
                address_txs[wallet_tx.wallet.address] = outs_list
            self.find_similar_accumulation(wallet_tx, address_txs[wallet_tx.wallet.address])

    def get_alert_reason(self, address) -> str:
        # TODO split
        """
        Get alert reason
        """
        if self.CURRENCY in ERC20_CURRENCIES:
            accumulation_transaction = AccumulationTransaction.objects.filter(
                accumulation_state__wallet__address=address,
                accumulation_state__wallet__currency=self.CURRENCY,
                accumulation_state__wallet__blockchain_currency=self.BLOCKCHAIN_CURRENCY,
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

    def find_similar_accumulation(self, wallet_tx: WalletTransactions, address_txs):
        """
        Try to find tx with identical amount as wallet transaction(deposit)
        """
        timeout_datetime = wallet_tx.created + datetime.timedelta(seconds=self.ACCUMULATION_TIMEOUT)
        now = timezone.now()

        # filter txs by time and address
        filtered_txs = []
        offset_time = wallet_tx.created - datetime.timedelta(seconds=self.OFFSET_SECONDS)

        for i, tx in enumerate(address_txs):
            if tx['created'] <= offset_time or timeout_datetime < tx['created']:
                continue
            if tx['from'].lower() == wallet_tx.wallet.address.lower():
                filtered_txs.append((i, tx))

        if not filtered_txs:
            # timeout frame filled
            if now > timeout_datetime:
                wallet_tx.state = WalletTransactions.STATE_NOT_ACCUMULATED
                wallet_tx.save()

            return

        # погрешность
        for i, tx in filtered_txs:
            # Accumulate to safe address
            if tx['to'].lower() == self.SAFE_ADDRESS.lower():
                if tx['value'] + self.DELTA_AMOUNT >= wallet_tx.amount:
                    wallet_tx.state = WalletTransactions.STATE_ACCUMULATED
                else:
                    wallet_tx.state = WalletTransactions.STATE_WRONG_AMOUNT

            # Accumulate to wrong address
            else:
                wallet_tx.state = WalletTransactions.STATE_WRONG_ACCUMULATION
                wallet_tx.save()

            # delete entry in accumulated
            address_txs[i]['value'] -= wallet_tx.amount
            if wallet_tx.state == WalletTransactions.STATE_WRONG_ACCUMULATION:

                if address_txs[i]['value'] < 0:
                    continue

            if address_txs[i]['value'] <= 0:
                del address_txs[i]

            wallet_tx.save()
            return
