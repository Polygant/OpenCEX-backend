
import datetime
from typing import List

from django.utils import timezone

from core.models import WalletTransactions
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from cryptocoins.models.scoring import ScoringSettings


class AccumulationManager:
    @staticmethod
    def get_wallet_transaction_by_id(wallet_transaction_id) -> WalletTransactions:
        return WalletTransactions.objects.select_related(
            'wallet',
        ).get(
            id=wallet_transaction_id,
        )

    @staticmethod
    def get_waiting_for_kyt_check(blockchain_currency: str):
        now = timezone.now()
        return WalletTransactions.objects.filter(
            wallet__blockchain_currency=blockchain_currency,
            state__in=[
                WalletTransactions.STATE_WAITING_FOR_KYT_APPROVE,
            ],
            # todo check scoring time for tokens too
            created__lte=now - datetime.timedelta(seconds=ScoringSettings.get_deffered_scoring_time(blockchain_currency)),
        )

    @staticmethod
    def get_waiting_for_accumulation(blockchain_currency):
        return WalletTransactions.get_ready_for_accumulation(blockchain_currency)

    @staticmethod
    def get_waiting_for_external_accumulation(blockchain_currency):
        return WalletTransactions.objects.filter(
            wallet__blockchain_currency=blockchain_currency,
            state__in=WalletTransactions.ACCUMULATION_READY_STATES,
            external_accumulation_address__isnull=False,
        )

    @staticmethod
    def get_last_gas_deposit_tx(wallet_transaction: WalletTransactions):
        return wallet_transaction.accumulationtransaction_set.filter(
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            tx_state=AccumulationTransaction.STATE_COMPLETED,
        ).order_by(
            '-updated',
        ).first()

    @staticmethod
    def get_external_accumulation_addresses(currencies: list) -> List[str]:
        return list(WalletTransactions.objects.select_related(
            'wallet',
        ).filter(
            currency__in=currencies,
            state__in=WalletTransactions.ACCUMULATION_READY_STATES + [WalletTransactions.STATE_ACCUMULATION_IN_PROGRESS],
            external_accumulation_address__isnull=False,
        ).values_list('external_accumulation_address', flat=True))
