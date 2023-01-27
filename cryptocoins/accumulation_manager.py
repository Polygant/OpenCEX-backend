import datetime

from django.db import transaction
from django.utils import timezone

from core.models.cryptocoins import UserWallet
from cryptocoins.models import AccumulationState, AccumulationTransaction


class AccumulationManager:

    @property
    def model(self):
        """
        Model's proxy for accessing QS
        """
        return AccumulationState

    def get_by_id(self, accumulation_state_id) -> AccumulationState:
        return self.model.objects.select_related(
            'wallet',
        ).get(
            id=accumulation_state_id,
        )

    @transaction.atomic
    def set_need_check(self, wallet: UserWallet):
        """
        This state indicates balance recheck is needed for this wallet
        """
        state = AccumulationState.STATE_WAITING_FOR_CHECK
        if wallet.block_type == UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION:
            state = AccumulationState.STATE_ACCUMULATION_BLOCKED

        accumulation_state, created = self.model.objects.get_or_create(
            wallet_id=wallet.id,
            defaults={
                'wallet_id': wallet.id,
                'state': state,
            }
        )

        if not created:
            accumulation_state.state = state
            accumulation_state.save(update_fields=['state', 'updated'])
        return accumulation_state if accumulation_state.state == AccumulationState.STATE_WAITING_FOR_CHECK else None

    def get_waiting_for_check(self, blockchain_currency):
        return self.model.objects.filter(
            state=AccumulationState.STATE_WAITING_FOR_CHECK,
            wallet__blockchain_currency=blockchain_currency
        ).select_related('wallet')

    def get_stuck(self, blockchain_currency):
        return self.model.objects.filter(
            state__in=[
                AccumulationState.STATE_GAS_REQUIRED,
                AccumulationState.STATE_WAITING_FOR_GAS,
                AccumulationState.STATE_READY_FOR_ACCUMULATION,
                AccumulationState.STATE_ACCUMULATION_IN_PROCESS,
            ],
            updated__lt=timezone.now() - datetime.timedelta(minutes=2),
            wallet__blockchain_currency=blockchain_currency
        ).select_related('wallet')

    def get_last_gas_deposit_tx(self, accumulation_state_id):
        return AccumulationTransaction.objects.filter(
            accumulation_state_id=accumulation_state_id,
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
            tx_state=AccumulationTransaction.STATE_COMPLETED,
            updated__gte=timezone.now() - datetime.timedelta(seconds=90)
        ).order_by(
            '-updated',
        ).first()

    def get_last_accumulation_transaction(self, accumulation_state_id):
        return AccumulationTransaction.objects.filter(
            accumulation_state_id=accumulation_state_id,
        ).order_by(
            '-updated',
        ).first()
