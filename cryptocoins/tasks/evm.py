from celery import shared_task

from cryptocoins.evm.manager import evm_handlers_manager
from cryptocoins.exceptions import RetryRequired


@shared_task
def process_new_blocks_task(currency_code):
    evm_handlers_manager.get_handler(currency_code).process_new_blocks()


# @shared_task(bind=True)
# def process_block_task(currency_code):
#     evm_handlers_manager.get_handler(currency_code).process_block()



@shared_task
def check_tx_withdrawal_task(currency_code, withdrawal_id, tx_data):
    evm_handlers_manager.get_handler(currency_code).check_tx_withdrawal(withdrawal_id, tx_data)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def process_coin_deposit_task(currency_code, tx_data: dict):
    evm_handlers_manager.get_handler(currency_code).process_coin_deposit(tx_data)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def process_tokens_deposit_task(currency_code, tx_data: dict):
    evm_handlers_manager.get_handler(currency_code).process_tokens_deposit(tx_data)


@shared_task
def process_payouts_task(currency_code, password, withdrawals_ids=None):
    evm_handlers_manager.get_handler(currency_code).process_payouts(password, withdrawals_ids)


@shared_task
def withdraw_coin_task(currency_code, withdrawal_request_id, password):
    evm_handlers_manager.get_handler(currency_code).withdraw_coin(withdrawal_request_id, password)


@shared_task
def withdraw_tokens_task(currency_code, withdrawal_request_id, password):
    evm_handlers_manager.get_handler(currency_code).withdraw_tokens(withdrawal_request_id, password)


@shared_task
def check_deposit_scoring_task(currency_code, wallet_transaction_id):
    evm_handlers_manager.get_handler(currency_code).check_deposit_scoring(wallet_transaction_id)


@shared_task
def check_balances_task(currency_code):
    evm_handlers_manager.get_handler(currency_code).check_balances()


@shared_task
def check_balance_task(currency_code, wallet_transaction_id):
    evm_handlers_manager.get_handler(currency_code).check_balance(wallet_transaction_id)


@shared_task
def accumulate_coin_task(currency_code, wallet_transaction_id):
    evm_handlers_manager.get_handler(currency_code).accumulate_coin(wallet_transaction_id)


@shared_task
def accumulate_tokens_task(currency_code, wallet_transaction_id):
    evm_handlers_manager.get_handler(currency_code).accumulate_tokens(wallet_transaction_id)


@shared_task
def send_gas_task(currency_code, wallet_transaction_id):
    evm_handlers_manager.get_handler(currency_code).send_gas(wallet_transaction_id)


@shared_task
def accumulate_dust_task(currency_code):
    evm_handlers_manager.get_handler(currency_code).accumulate_dust()
