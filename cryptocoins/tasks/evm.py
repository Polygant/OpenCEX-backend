from celery import shared_task

from cryptocoins.exceptions import RetryRequired


@shared_task
def process_new_blocks_task(currency_code):
    pass
    # Manager.get_manager(currency_code).process_new_blocks()


@shared_task(bind=True)
def process_block_task(currency_code):
    pass
    #Manager.get_manager(currency_code).process_block()


@shared_task
def check_tx_withdrawal_task(currency_code, withdrawal_id, tx_data):
    pass
    #Manager.get_manager(currency_code).check_tx_withdrawal(withdrawal_id, tx_data)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def process_coin_deposit_task(currency_code, tx_data: dict):
    pass
    # Manager.get_manager(currency_code).process_blockchain_coin_deposit(tx_data)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def process_tokens_deposit_task(currency_code, tx_data: dict):
    pass
    # Manager.get_manager(currency_code).process_token_deposit(tx_data)


@shared_task
def process_payouts_task(currency_code, password, withdrawals_ids=None):
    pass
    # Manager.get_manager(currency_code).process_payouts(password, withdrawals_ids)

@shared_task
def withdraw_coin_task(currency_code, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
    pass
    # Manager.get_manager(currency_code).process_payouts(password, withdrawals_ids)

@shared_task
def withdraw_tokens_task(currency_code, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
    pass
    # Manager.get_manager(currency_code).process_payouts(password, withdrawals_ids)

@shared_task
def check_deposit_scoring_task(currency_code, wallet_transaction_id):
    pass

@shared_task
def check_balances_task(currency_code):
    pass


@shared_task
def check_balance_task(currency_code):
    pass


@shared_task
def accumulate_coin_task(currency_code, wallet_transaction_id):
    pass


@shared_task
def accumulate_tokens_task(currency_code, wallet_transaction_id):
    pass


@shared_task
def send_gas_task(currency_code, wallet_transaction_id, old_tx_data=None, old_tx_hash=None):
    pass

