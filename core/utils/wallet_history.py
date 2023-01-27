import logging
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist

from core.models.inouts.sci import COMPLETED as PAYGATE_TOPUP_COMPLETED
from core.models.inouts.sci import FAILED as PAYGATE_TOPUP_FAILED
from core.models.inouts.sci import PENDING as PAYGATE_TOPUP_PENDING
from core.models.inouts.sci import PayGateTopup
from core.models.inouts.transaction import REASON_LOCK, REASON_STAKE_EARNINGS
from core.models.inouts.transaction import REASON_MANUAL_TOPUP
from core.models.inouts.transaction import REASON_ORDER_REVERT_CHARGE
from core.models.inouts.transaction import REASON_ORDER_REVERT_RETURN
from core.models.inouts.transaction import REASON_PAYGATE_REVERT_CHARGE
from core.models.inouts.transaction import REASON_PAYGATE_REVERT_RETURN
from core.models.inouts.transaction import REASON_REF_BONUS
from core.models.inouts.transaction import REASON_STAKE
from core.models.inouts.transaction import REASON_TOPUP
from core.models.inouts.transaction import REASON_TOPUP_MERCHANT
from core.models.inouts.transaction import REASON_UNLOCK
from core.models.inouts.transaction import REASON_UNSTAKE
from core.models.inouts.transaction import REASON_WALLET_REVERT_CHARGE
from core.models.inouts.transaction import REASON_WALLET_REVERT_RETURN
from core.models.inouts.transaction import REASON_WITHDRAWAL
from core.models.inouts.transaction import TRANSACTION_CANCELED
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.transaction import TRANSACTION_PENDING
from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import CANCELLED as WITHDRAWAL_REQUEST_CANCELLED
from core.models.inouts.withdrawal import COMPLETED as WITHDRAWAL_REQUEST_COMPLETED
from core.models.inouts.withdrawal import CREATED as WITHDRAWAL_REQUEST_CREATED
from core.models.inouts.withdrawal import FAILED as WITHDRAWAL_REQUEST_FAILED
from core.models.inouts.withdrawal import PENDING as WITHDRAWAL_REQUEST_PENDING
from core.models.inouts.withdrawal import VERIFYING as WITHDRAWAL_REQUEST_VERIFYING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.models.wallet_history import WalletHistoryItem
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


def create_or_update_wallet_history_item_from_transaction(transaction, save=True, instance=None) -> Optional[WalletHistoryItem]:
    operation_type = _get_operation_type_by_tx_reason(transaction.reason)

    # does transaction fits by type?
    if operation_type is None:
        log.debug('Not deposit or withdrawal transaction: #%s. Skipping', transaction.id)
        return None

    # create or update
    try:
        instance: WalletHistoryItem = instance or transaction.wallethistoryitem
        # TODO check this moment
        # instance.operation_type = operation_type
        log.debug('Updating wallet history item #%s from transaction #%s', instance.id, transaction.id)

    except ObjectDoesNotExist:
        log.debug('Creating wallet history item from transaction #%s', transaction.id)
        instance = WalletHistoryItem(
            user_id=transaction.user_id,
            transaction=transaction,
            operation_type=operation_type,
            currency=transaction.currency,
            amount=to_decimal(transaction.amount),
            created=transaction.created,
            updated=transaction.updated,
        )

    # TODO replace with fiat
    is_fiat = False
    # is fiat
    if is_fiat:
        # deposit
        if operation_type == WalletHistoryItem.OPERATION_TYPE_DEPOSIT:
            log.debug('Processing transaction #%s as %s deposit', transaction.id, transaction.currency.CODE)

            instance.state = _get_state_by_tx_state(transaction)


        # withdrawal
        else:
            log.debug('Processing transaction #%s as AND withdrawal', transaction.id)
            # instance.state = _get_state_by_tx_state(transaction)

            withdrawal_request = WithdrawalRequest.objects.filter(transaction=transaction).first()

            if withdrawal_request is not None:
                instance.state = _get_state_by_withdrawal_request(withdrawal_request)
                instance.paygate_id = withdrawal_request.sci_gate_id

                instance.paygate_method = _get_payment_method_from_paygate_id(withdrawal_request.sci_gate_id,
                                                                              withdrawal_request.data)

                instance.address = ''

                if withdrawal_request.txid is not None:
                    instance.tx_hash = withdrawal_request.txid

    # is crypto
    else:
        # deposit
        if operation_type in (WalletHistoryItem.OPERATION_TYPE_DEPOSIT, WalletHistoryItem.OPERATION_TYPE_MERCHANT):
            log.debug('Processing transaction #%s as crypto deposit', transaction.id)

            wallet_transaction = WalletTransactions.objects.filter(transaction=transaction).first()

            if wallet_transaction is not None:
                instance.address = wallet_transaction.wallet.address

                if wallet_transaction.tx_hash:
                    instance.tx_hash = wallet_transaction.tx_hash

            instance.state = _get_state_by_tx_state(transaction)

        # withdrawal
        else:
            log.debug('Processing transaction #%s as crypto withdrawal', transaction.id)
            withdrawal_request = WithdrawalRequest.objects.filter(transaction=transaction).first()

            if withdrawal_request is not None:
                instance.state = _get_state_by_withdrawal_request(withdrawal_request)

                instance.address = withdrawal_request.data.get('destination', '')
                instance.tx_hash = withdrawal_request.txid or ''

    # is referral bonus topup?
    if transaction.reason == REASON_REF_BONUS:
        instance.paygate_method = WalletHistoryItem.PAYGATE_METHOD_REF_BONUS
        instance.state = _get_state_by_tx_state(transaction)

    if operation_type in (
            WalletHistoryItem.OPERATION_TYPE_REVERT_RETURN,
            WalletHistoryItem.OPERATION_TYPE_REVERT_CHARGE,
            WalletHistoryItem.OPERATION_TYPE_REVERT,
            WalletHistoryItem.OPERATION_TYPE_STAKE,
            WalletHistoryItem.OPERATION_TYPE_UNSTAKE,
            WalletHistoryItem.OPERATION_TYPE_LOCK,
            WalletHistoryItem.OPERATION_TYPE_UNLOCK,
            WalletHistoryItem.OPERATION_TYPE_STAKE_EARNINGS,
    ):
        instance.state = _get_state_by_tx_state(transaction)

    if save:
        instance.save()

    return instance


def _get_operation_type_by_tx_reason(reason: int) -> Optional[int]:
    """
    Translate Transaction reason into wallet operation type
    """
    operation_type = None

    if reason in (REASON_TOPUP_MERCHANT, ):
        operation_type = WalletHistoryItem.OPERATION_TYPE_MERCHANT

    if reason in (REASON_ORDER_REVERT_CHARGE, REASON_ORDER_REVERT_RETURN, ):
        operation_type = WalletHistoryItem.OPERATION_TYPE_REVERT

    if reason in (
            REASON_ORDER_REVERT_CHARGE,
            REASON_PAYGATE_REVERT_CHARGE,
            REASON_WALLET_REVERT_CHARGE,
    ):
        operation_type = WalletHistoryItem.OPERATION_TYPE_REVERT_CHARGE

    if reason in (
            REASON_ORDER_REVERT_RETURN,
            REASON_PAYGATE_REVERT_RETURN,
            REASON_WALLET_REVERT_RETURN,
    ):
        operation_type = WalletHistoryItem.OPERATION_TYPE_REVERT_RETURN

    if reason in (REASON_TOPUP, REASON_REF_BONUS, REASON_MANUAL_TOPUP):
        operation_type = WalletHistoryItem.OPERATION_TYPE_DEPOSIT

    elif reason in (REASON_WITHDRAWAL, ):
        operation_type = WalletHistoryItem.OPERATION_TYPE_WITHDRAWAL

    elif reason == REASON_STAKE:
        operation_type = WalletHistoryItem.OPERATION_TYPE_STAKE

    elif reason == REASON_UNSTAKE:
        operation_type = WalletHistoryItem.OPERATION_TYPE_UNSTAKE

    elif reason == REASON_LOCK:
        operation_type = WalletHistoryItem.OPERATION_TYPE_LOCK

    elif reason == REASON_UNLOCK:
        operation_type = WalletHistoryItem.OPERATION_TYPE_UNLOCK

    elif reason == REASON_STAKE_EARNINGS:
        operation_type = WalletHistoryItem.OPERATION_TYPE_STAKE_EARNINGS

    return operation_type


def _get_state_by_pay_gate_topup(pay_gate_topup: PayGateTopup) -> int:
    """
    Translate PayGateTopup state into wallet operation state
    """
    state = WalletHistoryItem.STATE_UNKNOWN

    if pay_gate_topup.state == PAYGATE_TOPUP_PENDING:
        state = WalletHistoryItem.STATE_PENDING

    elif pay_gate_topup.state == PAYGATE_TOPUP_COMPLETED:
        state = WalletHistoryItem.STATE_DONE

    elif pay_gate_topup.state == PAYGATE_TOPUP_FAILED:
        state = WalletHistoryItem.STATE_FAILED

    return state


def _get_state_by_withdrawal_request(wr: WithdrawalRequest) -> int:
    """
    Translate WithdrawalRequest state into wallet operation state
    """
    state = WalletHistoryItem.STATE_UNKNOWN

    if wr.state in [WITHDRAWAL_REQUEST_CREATED, WITHDRAWAL_REQUEST_PENDING]:
        state = WalletHistoryItem.STATE_PENDING

    if wr.state == WITHDRAWAL_REQUEST_VERIFYING:
        state = WalletHistoryItem.STATE_VERIFYING

    elif wr.state == WITHDRAWAL_REQUEST_COMPLETED:
        state = WalletHistoryItem.STATE_DONE

    elif wr.state == WITHDRAWAL_REQUEST_FAILED:
        state = WalletHistoryItem.STATE_FAILED

    elif wr.state == WITHDRAWAL_REQUEST_CANCELLED:
        state = WalletHistoryItem.STATE_CANCELED

    if wr.state == WITHDRAWAL_REQUEST_CREATED and wr.confirmed is False:
        state = WalletHistoryItem.STATE_WAIT_CONFIRMATION

    elif wr.state == WITHDRAWAL_REQUEST_CREATED and wr.confirmed is True:
        state = WalletHistoryItem.STATE_TO_BE_SENT

    return state


def _get_state_by_tx_state(transaction) -> int:
    """
    Translate transaction state into wallet operation state
    """
    state = WalletHistoryItem.STATE_PENDING

    if transaction.state == TRANSACTION_PENDING:
        state = WalletHistoryItem.STATE_PENDING

    elif transaction.state == TRANSACTION_CANCELED:
        state = WalletHistoryItem.STATE_CANCELED

    elif transaction.state == TRANSACTION_COMPLETED:
        state = WalletHistoryItem.STATE_DONE

    if transaction.reason in [
        REASON_WALLET_REVERT_RETURN,
        REASON_WALLET_REVERT_CHARGE,
        REASON_PAYGATE_REVERT_RETURN,
        REASON_PAYGATE_REVERT_CHARGE,
    ]:
        state = WalletHistoryItem.STATE_REVERTED

    return state


def _get_payment_method_from_paygate_id(paygate_id: int, data: dict) -> Optional[str]:
    method = None

    # interkassa
    if paygate_id == 1:
        internal_method = data.get('method', '').lower()
        if internal_method == 'qiwi':
            method = WalletHistoryItem.PAYGATE_METHOD_QIWI
        elif internal_method == 'mastercard':
            method = WalletHistoryItem.PAYGATE_METHOD_MASTERCARD
        elif internal_method == 'visa':
            method = WalletHistoryItem.PAYGATE_METHOD_VISA

    # advcash
    elif paygate_id == 2:
        # supports only account method
        method = WalletHistoryItem.PAYGATE_METHOD_ACCOUNT

    # payeer
    elif paygate_id == 3:
        internal_method = data.get('payment_system', '').lower()
        if internal_method == 'payeer':
            method = WalletHistoryItem.PAYGATE_METHOD_ACCOUNT
        elif internal_method == 'mastercard':
            method = WalletHistoryItem.PAYGATE_METHOD_MASTERCARD
        elif internal_method == 'visa':
            method = WalletHistoryItem.PAYGATE_METHOD_VISA

    return method


def _get_recipient_from_paygate_id(paygate_id: int, data: dict) -> Optional[str]:
    recipient = None

    # interkassa
    if paygate_id == 1:
        internal_method = data.get('method', '').lower()
        # qiwi format
        if internal_method == 'qiwi':
            if data.get('details', {}).get('phone'):
                recipient = data['details']['phone']
            elif data.get('details', {}).get('user'):
                recipient = data['details']['user']

        # card format
        else:
            if data.get('details', {}).get('user'):
                recipient = data['details']['user']

    # advcash
    elif paygate_id == 2:
        recipient = data.get('recipient')

    # payeer
    elif paygate_id == 3:
        recipient = data.get('recipient_account')

    return recipient