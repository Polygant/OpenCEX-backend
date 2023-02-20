import logging
import time
from django.utils import timezone
import datetime

from celery import group, shared_task
from django.conf import settings
from web3 import Web3

from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import PENDING as WR_PENDING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.coins.eth import ETH_CURRENCY
from cryptocoins.coins.eth.ethereum import EthTransaction, ethereum_manager
from cryptocoins.exceptions import RetryRequired
from cryptocoins.models import ScoringSettings
from cryptocoins.models.accumulation_details import AccumulationDetails
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from cryptocoins.scoring.manager import ScoreManager
from cryptocoins.utils.commons import (
    load_last_processed_block_id,
    store_last_processed_block_id,
    get_withdrawal_requests_to_process,
    get_withdrawal_requests_pending,
)
from cryptocoins.utils.infura import w3
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal

log = logging.getLogger(__name__)
accumulation_manager = AccumulationManager()

DEFAULT_BLOCK_ID_DELTA = 1000
ETH_SAFE_ADDR = w3.toChecksumAddress(settings.ETH_SAFE_ADDR)
ERC20_TOKEN_CURRENCIES = ethereum_manager.registered_token_currencies
ERC20_TOKEN_CONTRACT_ADDRESSES = ethereum_manager.registered_token_addresses


@shared_task
def eth_process_new_blocks():
    current_block_id = w3.eth.blockNumber
    default_block_id = current_block_id - DEFAULT_BLOCK_ID_DELTA
    last_processed_block_id = load_last_processed_block_id(
        currency=ETH_CURRENCY, default=default_block_id)

    if last_processed_block_id >= current_block_id:
        log.debug('Nothing to process since block #%s', current_block_id)
        return

    blocks_to_process = list(range(
        last_processed_block_id + 1,
        current_block_id + 1,
    ))
    blocks_to_process.insert(0, last_processed_block_id)

    if len(blocks_to_process) > 1:
        log.info('Need to process blocks #%s..#%s', last_processed_block_id + 1, current_block_id)
    else:
        log.info('Need to process block #%s', last_processed_block_id + 1)

    # make subtask group
    block_jobs = []

    for block_id in blocks_to_process:
        # block_jobs.append(eth_process_block.s(block_id))
        eth_process_block(block_id)

    # jobs_group = group(block_jobs)
    # jobs_group.apply_async()

    store_last_processed_block_id(currency=ETH_CURRENCY, block_id=current_block_id)


@shared_task(bind=True)
def eth_process_block(self, block_id):
    started_at = time.time()
    log.info('Processing block #%s', block_id)

    block = w3.eth.getBlock(block_id, full_transactions=True)

    if block is None:
        log.error('Failed to get block #%s, skip...', block_id)
        raise self.retry(max_retries=10, countdown=1)

    transactions = block.get('transactions', [])

    if len(transactions) == 0:
        log.info('Block #%s has no transactions, skipping', block_id)
        return

    log.info('Transactions count in block #%s: %s', block_id, len(transactions))

    eth_jobs = []
    erc20_jobs = []

    eth_withdrawal_requests_pending = get_withdrawal_requests_pending([ETH_CURRENCY])
    erc20_withdrawal_requests_pending = get_withdrawal_requests_pending(ERC20_TOKEN_CURRENCIES, blockchain_currency='ETH')

    eth_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                            for i in eth_withdrawal_requests_pending}
    eth_withdrawal_requests_pending_txs = {v: k for k,
                                           values in eth_withdrawals_dict.items() for v in values}

    erc20_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                              for i in erc20_withdrawal_requests_pending}
    erc20_withdrawal_requests_pending_txs = {
        v: k for k, values in erc20_withdrawals_dict.items() for v in values}

    check_eth_withdrawal_jobs = []
    check_erc20_withdrawal_jobs = []

    # Withdrawals
    for tx_data in transactions:
        tx = EthTransaction.from_node(tx_data)
        if not tx:
            continue

        # is ETH withdrawal request tx?
        if tx.hash in eth_withdrawal_requests_pending_txs:
            withdrawal_id = eth_withdrawal_requests_pending_txs[tx.hash]
            check_eth_withdrawal_jobs.append(check_tx_withdrawal.s(withdrawal_id, tx.as_dict()))
            continue

        # is ERC20 withdrawal request tx?
        if tx.hash in erc20_withdrawal_requests_pending_txs:
            withdrawal_id = erc20_withdrawal_requests_pending_txs[tx.hash]
            check_erc20_withdrawal_jobs.append(check_tx_withdrawal.s(withdrawal_id, tx.as_dict()))
            continue

    eth_addresses = set(ethereum_manager.get_user_addresses())
    eth_keeper = ethereum_manager.get_keeper_wallet()
    eth_gas_keeper = ethereum_manager.get_gas_keeper_wallet()

    eth_addresses_deps = set(eth_addresses)
    eth_addresses_deps.add(ETH_SAFE_ADDR)

    # Deposits
    for tx_data in transactions:
        tx = EthTransaction.from_node(tx_data)
        if not tx:
            continue

        if tx.to_addr is None:
            continue

        if tx.to_addr in eth_addresses_deps:
            # process ETH deposit
            if not tx.contract_address:
                eth_jobs.append(eth_process_eth_deposit.s(tx.as_dict()))
            # process ERC20 deposit
            else:
                erc20_jobs.append(eth_process_erc20_deposit.s(tx.as_dict()))

    if eth_jobs:
        log.info('Need to check ETH deposits count: %s', len(eth_jobs))
        group(eth_jobs).apply_async()

    if erc20_jobs:
        log.info('Need to check ERC20 deposits count: %s', len(erc20_jobs))
        group(erc20_jobs).apply_async()

    if check_eth_withdrawal_jobs:
        log.info('Need to check ETH withdrawals count: %s', len(check_eth_withdrawal_jobs))
        group(check_eth_withdrawal_jobs).apply_async()

    if check_erc20_withdrawal_jobs:
        log.info('Need to check ERC20 withdrawals count: %s', len(check_eth_withdrawal_jobs))
        group(check_erc20_withdrawal_jobs).apply_async()

    # check accumulations
    for tx_data in transactions:
        tx = EthTransaction.from_node(tx_data)
        if not tx:
            continue

        # checks only exchange addresses withdrawals
        if tx.from_addr not in eth_addresses:
            continue

        # skip txs from keepers
        if tx.from_addr in [eth_keeper.address, eth_gas_keeper.address, ETH_SAFE_ADDR]:
            continue

        # checks only if currency flows outside the exchange
        if tx.to_addr in eth_addresses:
            continue

        # check ERC20 accumulations
        if tx.contract_address:
            token = ethereum_manager.get_token_by_address(tx.contract_address)

            accumulation_details, created = AccumulationDetails.objects.get_or_create(
                txid=tx.hash,
                defaults=dict(
                    txid=tx.hash,
                    from_address=tx.from_addr,
                    to_address=tx.to_addr,
                    currency=ETH_CURRENCY,
                    token_currency=token.currency,
                    state=AccumulationDetails.STATE_COMPLETED,
                )
            )
            if not created:
                log.info(f'Found accumulation {token.currency} from {tx.from_addr} to {tx.to_addr}')
                accumulation_details.to_address = tx.to_addr
                accumulation_details.complete()
            else:
                log.info(f'Unexpected accumulation {token.currency} from {tx.from_addr} to {tx.to_addr}')

        # check ETH accumulations
        else:
            accumulation_details, created = AccumulationDetails.objects.get_or_create(
                txid=tx.hash,
                defaults=dict(
                    txid=tx.hash,
                    from_address=tx.from_addr,
                    to_address=tx.to_addr,
                    currency=ETH_CURRENCY,
                    state=AccumulationDetails.STATE_COMPLETED,
                )
            )
            if not created:
                log.info(f'Found accumulation ETH from {tx.from_addr} to {tx.to_addr}')
                # Use to_address only from node
                accumulation_details.to_address = w3.toChecksumAddress(tx.to_addr)
                accumulation_details.complete()
            else:
                log.info(f'Unexpected accumulation ETH from {tx.from_addr} to {tx.to_addr}')

    execution_time = time.time() - started_at
    log.info('Block #%s processed in %.2f sec. (ETH TX count: %s, ERC20 TX count: %s, WR TX count: %s)',
             block_id, execution_time, len(eth_jobs), len(erc20_jobs),
             len(check_erc20_withdrawal_jobs) + len(check_eth_withdrawal_jobs))


@shared_task
def check_tx_withdrawal(withdrawal_id, tx_data):
    tx = EthTransaction(tx_data)

    withdrawal_request = WithdrawalRequest.objects.filter(
        id=withdrawal_id,
        state=WR_PENDING,
    ).first()

    if withdrawal_request is None:
        log.warning('Invalid withdrawal request state for TX %s', tx.hash)
        return

    withdrawal_request.txid = tx.hash

    if not ethereum_manager.is_valid_transaction(tx.hash):
        withdrawal_request.fail()
        return

    withdrawal_request.complete()


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def eth_process_eth_deposit(tx_data: dict, deffered=False):
    """
    Process ETH deposit, excepting inner gas deposits, etc
    """
    log.info('Processing eth deposit: %s', tx_data)
    tx = EthTransaction(tx_data)
    amount = ethereum_manager.get_amount_from_base_denomination(tx.value)

    # skip if failed
    if not ethereum_manager.is_valid_transaction(tx.hash):
        log.error(f'ETH deposit transaction {tx.hash} is invalid or failed')
        return

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(amount, 'ETH'):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time('ETH')
        eth_process_eth_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    # is accumulation tx?
    if tx.to_addr == ETH_SAFE_ADDR:
        accumulation_transaction = AccumulationTransaction.objects.filter(
            tx_hash=tx.hash,
        ).first()

        if accumulation_transaction is None:
            log.error(f'Accumulation TX {tx.hash} not exist')
            return

        if accumulation_transaction.tx_state == AccumulationTransaction.STATE_COMPLETED:
            log.info(f'Accumulation TX {tx.hash} already processed')
            return

        accumulation_transaction.complete()

        log.info(f'Tx {tx.hash} is ETH accumulation')
        return

    eth_keeper = ethereum_manager.get_keeper_wallet()
    eth_gas_keeper = ethereum_manager.get_gas_keeper_wallet()
    # is inner gas deposit?
    if tx.from_addr == eth_gas_keeper.address:
        accumulation_transaction = AccumulationTransaction.objects.filter(
            tx_hash=tx.hash,
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
        ).first()

        if accumulation_transaction is None:
            log.error(f'Gas accumulation TX {tx.hash} not found')
            return

        if accumulation_transaction.tx_state == AccumulationTransaction.STATE_COMPLETED:
            log.info(f'Accumulation TX {tx.hash} already processed as token gas')
            return

        log.info(f'Tx {tx.hash} is gas deposit')
        accumulation_transaction.complete(is_gas=True)
        accumulate_erc20.apply_async([accumulation_transaction.accumulation_state.id, True])
        return

    db_wallet = ethereum_manager.get_wallet_db_instance(ETH_CURRENCY, tx.to_addr)
    if db_wallet is None:
        log.error(f'Wallet ETH {tx.to_addr} not exists or blocked')
        return

    # is already processed?
    db_wallet_transaction = WalletTransactions.objects.filter(
        tx_hash__iexact=tx.hash,
        wallet_id=db_wallet.id,
    ).first()

    if db_wallet_transaction is not None:
        log.warning('TX %s already processed as ETH deposit', tx.hash)
        return

    # make deposit
    # check for keeper deposit
    if db_wallet.address == eth_keeper.address:
        log.info('TX %s is keeper ETH deposit: %s', tx.hash, amount)
        return

    # check for gas keeper deposit
    if db_wallet.address == eth_gas_keeper.address:
        log.info('TX %s is gas keeper ETH deposit: %s', tx.hash, amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(tx.hash, tx.to_addr, amount, ETH_CURRENCY.code)

    if amount < ethereum_manager.deposit_min_amount and amount < ethereum_manager.accumulation_min_balance:
        log.warning('Deposit %s less than min required, skipping', amount)
        accumulation_manager.set_need_check(db_wallet)
        # accumulate later when amount >= min_dep_limit
        return

    WalletTransactions.objects.create(
        wallet=db_wallet,
        tx_hash=tx.hash,
        amount=amount,
        currency=ETH_CURRENCY,
        state=WalletTransactions.STATE_NOT_CHECKED if is_scoring_ok else WalletTransactions.STATE_BAD_DEPOSIT,
    )
    if is_scoring_ok:
        # set check state
        accumulation_state = accumulation_manager.set_need_check(db_wallet)
        if accumulation_state:
            check_balance.apply_async([accumulation_state.id, True])

        log.info('TX %s processed as %s ETH deposit', tx.hash, amount)
    else:
        log.warning('TX %s processed as %s ETH BAD deposit', tx.hash, amount)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def eth_process_erc20_deposit(tx_data: dict, deffered=False):
    """
    Process ERC20 deposit
    """
    log.info('Processing ERC20 deposit: %s', tx_data)
    tx = EthTransaction(tx_data)

    if not ethereum_manager.is_valid_transaction(tx.hash):
        log.warning('ERC20 deposit TX %s is failed or invalid', tx.hash)
        return

    token = ethereum_manager.get_token_by_address(tx.contract_address)
    token_to_addr = tx.to_addr
    token_amount = token.get_amount_from_base_denomination(tx.value)

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(token_amount, token.currency.code):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time(token.currency.code)
        eth_process_erc20_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    if token_to_addr == ETH_SAFE_ADDR:
        log.info(f'TX {tx.hash} is {token_amount} {token.currency} accumulation')

        accumulation_transaction = AccumulationTransaction.objects.filter(
            tx_hash=tx.hash,
        ).first()
        if accumulation_transaction is None:
            # accumulation from outside
            log.error('Token accumulation TX %s not exist', tx.hash)
            return

        accumulation_transaction.complete()
        return

    db_wallet = ethereum_manager.get_wallet_db_instance(token.currency, token_to_addr)
    if db_wallet is None:
        log.error(f'Wallet {token.currency} {token_to_addr} not exists or blocked')
        return

    db_wallet_transaction = WalletTransactions.objects.filter(
        tx_hash__iexact=tx.hash,
        wallet_id=db_wallet.id,
    ).first()
    if db_wallet_transaction is not None:
        log.warning('TX %s already processed as %s deposit', tx.hash, token.currency)
        return

    # check for keeper deposit
    eth_keeper = ethereum_manager.get_keeper_wallet()
    if db_wallet.address == eth_keeper.address:
        log.info('TX %s is keeper %s deposit: %s', tx.hash, token.currency, token_amount)
        return

    # check for gas keeper deposit
    eth_gas_keeper = ethereum_manager.get_gas_keeper_wallet()
    if db_wallet.address == eth_gas_keeper.address:
        log.info('TX %s is keeper %s deposit: %s', tx.hash, token.currency, token_amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(
            tx.hash,
            token_to_addr,
            token_amount,
            ETH_CURRENCY.code,
            token.currency.code,
        )

    # process ERC20 deposit
    if token_amount < token.deposit_min_amount and token_amount < token.accumulation_min_balance:
        log.warning('Deposit %s %s less than min required, skipping', token.currency, token_amount)
        accumulation_manager.set_need_check(db_wallet)
        # accumulate later when amount >= min_dep_limit
        return

    WalletTransactions.objects.create(
        wallet_id=db_wallet.id,
        tx_hash=tx.hash,
        amount=token_amount,
        currency=token.currency,
        state=WalletTransactions.STATE_NOT_CHECKED if is_scoring_ok else WalletTransactions.STATE_BAD_DEPOSIT,
    )
    if is_scoring_ok:
        # set check state
        accumulation_state = accumulation_manager.set_need_check(db_wallet)
        if accumulation_state:
            check_balance.apply_async([accumulation_state.id, True])

        log.info('TX %s processed as %s %s deposit', tx.hash, token_amount, token.currency)
    else:
        log.warning('TX %s processed as %s %s BAD deposit', tx.hash, token_amount, token.currency.code)


@shared_task
def process_payouts(password):
    eth_withdrawal_requests = get_withdrawal_requests_to_process(currencies=[ETH_CURRENCY])

    jobs_list = []

    if eth_withdrawal_requests:
        log.info('Need to process %s ETH withdrawals', len(eth_withdrawal_requests))

        for item in eth_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            withdraw_eth.apply_async([item.id, password])

    erc20_withdrawal_requests = get_withdrawal_requests_to_process(
        currencies=ERC20_TOKEN_CURRENCIES,
        blockchain_currency='ETH'
    )

    if erc20_withdrawal_requests:
        log.info('Need to process %s ERC20 withdrawals', len(erc20_withdrawal_requests))
        for item in erc20_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            withdraw_erc20.apply_async([item.id, password])


@shared_task
def withdraw_eth(withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
    if old_tx_data is None:
        old_tx_data = {}
    withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

    # todo: handle errors
    address = w3.toChecksumAddress(withdrawal_request.data.get('destination'))
    keeper = ethereum_manager.get_keeper_wallet()
    amount_wei = ethereum_manager.get_base_denomination_from_amount(withdrawal_request.amount)
    withdrawal_fee_wei = Web3.toWei(to_decimal(get_withdrawal_fee(ETH_CURRENCY, ETH_CURRENCY)), 'ether')
    amount_to_send_wei = amount_wei - withdrawal_fee_wei

    gas_price = ethereum_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)

    # todo: check min limit
    if amount_to_send_wei <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    keeper_balance = ethereum_manager.get_balance_in_base_denomination(keeper.address)
    if keeper_balance < (amount_to_send_wei + (gas_price * settings.ETH_TX_GAS)):
        log.warning('Keeper not enough ETH, skipping')
        return

    if old_tx_data:
        log.info('ETH withdrawal transaction to %s will be replaced', w3.toChecksumAddress(address))
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        if prev_tx_hash and ethereum_manager.get_transaction_receipt(prev_tx_hash):
            log.info('ETH TX %s sent. Do not need to replace.')
            return
    else:
        nonce = ethereum_manager.wait_for_nonce()
        tx_data = {
            'nonce': nonce,
            'gasPrice': gas_price,
            'gas': settings.ETH_TX_GAS,
            'from': w3.toChecksumAddress(keeper.address),
            'to': w3.toChecksumAddress(address),
            'value': amount_to_send_wei,
            'chainId': settings.ETH_CHAIN_ID,
        }

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)
    tx_hash = ethereum_manager.send_tx(
        private_key=private_key,
        to_address=address,
        amount=amount_to_send_wei,
        nonce=tx_data['nonce'],
        gasPrice=tx_data['gasPrice'],
    )

    if not tx_hash:
        log.error('Unable to send withdrawal TX')
        ethereum_manager.release_nonce()
        return

    withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
    withdrawal_txs_attempts.append(tx_hash.hex())

    withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))

    withdrawal_request.state = WR_PENDING
    withdrawal_request.our_fee_amount = ethereum_manager.get_amount_from_base_denomination(withdrawal_fee_wei)
    withdrawal_request.save(update_fields=['state', 'updated', 'our_fee_amount', 'data'])
    log.info('ETH withdrawal TX %s sent', tx_hash.hex())

    # wait tx processed
    try:
        ethereum_manager.wait_for_transaction_receipt(tx_hash, poll_latency=2)
        ethereum_manager.release_nonce()
    except RetryRequired:
        # retry with higher gas price
        withdraw_eth(withdrawal_request_id, password, old_tx_data=tx_data, prev_tx_hash=tx_hash)


@shared_task
def withdraw_erc20(withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
    if old_tx_data is None:
        old_tx_data = {}

    withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

    address = w3.toChecksumAddress(withdrawal_request.data.get('destination'))
    currency = withdrawal_request.currency

    token = ethereum_manager.get_token_by_symbol(currency)
    send_amount_wei = token.get_base_denomination_from_amount(withdrawal_request.amount)
    withdrawal_fee_wei = token.get_base_denomination_from_amount(token.withdrawal_fee)
    amount_to_send_wei = send_amount_wei - withdrawal_fee_wei
    if amount_to_send_wei <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    gas_price = ethereum_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)

    transfer_gas = token.get_transfer_gas_amount(address, amount_to_send_wei, True)

    keeper = ethereum_manager.get_keeper_wallet()
    keeper_eth_balance = ethereum_manager.get_balance_in_base_denomination(keeper.address)
    keeper_token_balance = token.get_base_denomination_balance(keeper.address)

    if keeper_eth_balance < gas_price * transfer_gas:
        log.warning('Keeper not enough ETH for gas, skipping')
        return

    if keeper_token_balance < amount_to_send_wei:
        log.warning('Keeper not enough %s, skipping', currency)
        return

    log.info('Amount to send: %s, gas price: %s, transfer gas: %s',
             amount_to_send_wei, gas_price, transfer_gas)

    if old_tx_data:
        log.info('%s withdrawal to %s will be replaced', currency.code, address)
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        if prev_tx_hash and ethereum_manager.get_transaction_receipt(prev_tx_hash):
            log.info('Token TX %s sent. Do not need to replace.')
            return
    else:
        nonce = ethereum_manager.wait_for_nonce()
        tx_data = {
            'chainId': settings.ETH_CHAIN_ID,
            'gas': transfer_gas,
            'gasPrice': gas_price,
            'nonce': nonce,
        }

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)
    tx_hash = token.send_token(private_key, address, amount_to_send_wei, **tx_data)

    if not tx_hash:
        log.error('Unable to send token withdrawal TX')
        ethereum_manager.release_nonce()
        return

    withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
    withdrawal_txs_attempts.append(tx_hash.hex())

    withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))
    withdrawal_request.state = WR_PENDING
    withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(withdrawal_fee_wei)

    withdrawal_request.save(update_fields=['state', 'updated', 'our_fee_amount', 'data'])
    log.info('%s withdrawal TX %s sent', currency, tx_hash.hex())

    # wait tx processed
    try:
        ethereum_manager.wait_for_transaction_receipt(tx_hash, poll_latency=2)
        ethereum_manager.release_nonce()
    except RetryRequired:
        # retry with higher gas price
        withdraw_erc20(withdrawal_request_id, password, old_tx_data=tx_data, prev_tx_hash=tx_hash)


@shared_task
def check_balances():
    jobs_list = []

    for item in accumulation_manager.get_waiting_for_check(blockchain_currency=ETH_CURRENCY):
        jobs_list.append(check_balance.s(item.id))

    for item in accumulation_manager.get_stuck(blockchain_currency=ETH_CURRENCY):
        jobs_list.append(check_balance.s(item.id))

    if jobs_list:
        log.info('Need to check count: %s', len(jobs_list))
        jobs_group = group(jobs_list)
        jobs_group.apply_async()


def is_gas_need(accumulation_state_id):
    acc_tx = accumulation_manager.get_last_gas_deposit_tx(accumulation_state_id)
    return not acc_tx
    #     is_pending = acc_tx.tx_state == AccumulationTransaction.STATE_PENDING
    #     is_gas_deposit = acc_tx.tx_type == AccumulationTransaction.TX_TYPE_GAS_DEPOSIT
    #     is_expired = acc_tx.created + datetime.timedelta(seconds=90) < timezone.now()
    #     if not is_expired or (is_pending and is_gas_deposit):
    #         return False
    # return True


@shared_task
def check_balance(accumulation_state_id, instant=False):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency

    # ETH
    if currency == ETH_CURRENCY:
        log.info('Checking ETH %s balance', address)
        amb = ethereum_manager.accumulation_min_balance
        if not instant:
            amount_wei = ethereum_manager.get_balance_in_base_denomination(address)
            amount = ethereum_manager.get_amount_from_base_denomination(amount_wei)
            accumulation_state.current_balance = amount
            log.info('Current ETH balance of %s is %s; Min accumulation amount is %s',
                     address, amount, amb)

            if not amount or amount < amb:
                log.info('Low balance of %s %s (current %s)', currency, address, amb)
                accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
                accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])
                return

        else:
            log.info(f'Try to accumulate ETH instant for {address}')
            accumulation_state.state = accumulation_manager.model.STATE_READY_FOR_ACCUMULATION
            accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])

        accumulate_eth.apply_async([accumulation_state.id, instant])

    # tokens
    else:
        log.info('Checking %s %s balance', currency, address)
        token = ethereum_manager.get_token_by_symbol(currency)
        if not instant:
            amount = token.get_balance(address)
            log.info('Balance of %s %s is %s; Min accumulation amount is %s',
                     currency, address, amount, token.accumulation_min_balance)

            accumulation_state.current_balance = amount

            # check min accumulation amount
            if not amount or amount < token.accumulation_min_balance:
                log.info(f'Low balance of {currency} {address}')
                accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
                accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])
                return

        if not is_gas_need(accumulation_state_id):
            log.info(f'Gas not required for {currency} {address}')
            accumulation_state.state = accumulation_manager.model.STATE_READY_FOR_ACCUMULATION
            accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])
            accumulate_erc20.apply_async([accumulation_state.id, instant])
            log.info(f'{address} balance checked')
        else:
            log.info(f'Gas required for {currency} {address}')
            accumulation_state.state = accumulation_manager.model.STATE_GAS_REQUIRED
            accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])
            send_gas.apply_async([accumulation_state.id])

    log.info(f'{address} balance checked')


@shared_task
def accumulate_eth(accumulation_state_id, instant=False):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address

    # recheck balance
    if instant:
        amount_wei = ethereum_manager.wait_for_balance_in_base_denomination(address)
    else:
        amount_wei = ethereum_manager.get_balance_in_base_denomination(address)

    amount = ethereum_manager.get_amount_from_base_denomination(amount_wei)
    log.info('Accumulation ETH from: %s; Balance: %s; Min acc balance:%s',
             address, amount, ethereum_manager.accumulation_min_balance)

    if not amount:
        log.warning('Current balance is 0 ETH. Need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    if amount < ethereum_manager.accumulation_min_balance:
        log.warning('Current balance less than minimum, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    accumulation_address = ethereum_manager.get_accumulation_address(amount)

    # we want to process our tx faster
    gas_price = ethereum_manager.gas_price_cache.get_increased_price()
    gas_amount = gas_price * settings.ETH_TX_GAS
    withdrawal_amount = amount_wei - gas_amount

    # in debug mode values can be very small
    if withdrawal_amount <= 0:
        log.error('ETH withdrawal amount invalid: %s',
                  ethereum_manager.get_amount_from_base_denomination(withdrawal_amount))
        accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
        accumulation_state.save(update_fields=['state', 'updated'])
        return

    # prepare tx
    wallet = ethereum_manager.get_user_wallet('ETH', address)
    nonce = ethereum_manager.client.eth.getTransactionCount(address)

    tx_hash = ethereum_manager.send_tx(
        private_key=wallet.private_key,
        to_address=accumulation_address,
        amount=withdrawal_amount,
        nonce=nonce,
        gasPrice=gas_price,
    )

    if not tx_hash:
        log.error('Unable to send accumulation TX')
        return

    AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=ethereum_manager.get_amount_from_base_denomination(withdrawal_amount),
        tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=tx_hash.hex(),
    )

    accumulation_state.state = accumulation_manager.model.STATE_ACCUMULATION_IN_PROCESS
    accumulation_state.save(update_fields=['state', 'updated'])

    AccumulationDetails.objects.create(
        currency=ETH_CURRENCY,
        txid=tx_hash.hex(),
        from_address=address,
        to_address=accumulation_address
    )

    log.info('Accumulation TX %s sent from %s to %s', tx_hash.hex(), wallet.address, accumulation_address)


@shared_task
def accumulate_erc20(accumulation_state_id, instant=False):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency

    gas_deposit_tx = accumulation_manager.get_last_gas_deposit_tx(accumulation_state_id)
    if gas_deposit_tx is None:
        log.warning(f'Gas deposit for {address} not found or in process')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    token = ethereum_manager.get_token_by_symbol(currency)
    # amount checks
    if instant:
        token_amount_wei = token.wait_for_balance_in_base_denomination(address)
    else:
        token_amount_wei = token.get_base_denomination_balance(address)
    token_amount = token.get_amount_from_base_denomination(token_amount_wei)

    if token_amount <= to_decimal(0):
        log.warning('Cant accumulate %s from: %s; Balance too low: %s;',
                    currency, address, token_amount)
        return

    accumulation_address = token.get_accumulation_address(token_amount)

    # we keep amount not as wei, it's more easy, so we need to convert it
    # checked_amount_wei = token.get_wei_from_amount(accumulation_state.current_balance)

    log.info(f'Accumulation {currency} from: {address}; Balance: {token_amount};')

    # if token_amount_wei < checked_amount_wei:
    #     log.warning('Token amount less than last checked, need to recheck')
    #     accumulation_manager.set_need_check(accumulation_state.wallet)
    #     return

    accumulation_gas_amount = ethereum_manager.get_base_denomination_from_amount(gas_deposit_tx.amount)
    eth_amount_wei = ethereum_manager.get_balance_in_base_denomination(address)

    if eth_amount_wei < accumulation_gas_amount:
        log.warning(f'Wallet ETH amount: {eth_amount_wei} less than gas needed '
                    f'{accumulation_gas_amount}, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    accumulation_gas_required_amount = token.get_transfer_gas_amount(
        accumulation_address,
        token_amount_wei,
    )

    # calculate from existing wallet eth amount
    gas_price = int(accumulation_gas_amount / accumulation_gas_required_amount)

    wallet = ethereum_manager.get_user_wallet(currency, address)
    nonce = w3.eth.getTransactionCount(address)

    tx_hash = token.send_token(
        wallet.private_key,
        accumulation_address,
        token_amount_wei,
        gas=accumulation_gas_required_amount,
        gasPrice=gas_price,
        nonce=nonce
    )

    if not tx_hash:
        log.error('Unable to send token accumulation TX')
        return

    AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=token.get_amount_from_base_denomination(token_amount_wei),
        tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=tx_hash.hex(),
    )
    accumulation_state.state = accumulation_manager.model.STATE_ACCUMULATION_IN_PROCESS
    accumulation_state.save(update_fields=['state', 'updated'])

    AccumulationDetails.objects.create(
        currency=ETH_CURRENCY,
        token_currency=currency,
        txid=tx_hash.hex(),
        from_address=address,
        to_address=accumulation_address,
    )

    log.info('Token accumulation TX %s sent from %s to: %s',
             tx_hash.hex(), wallet.address, accumulation_address)


@shared_task
def send_gas(accumulation_state_id, old_tx_data=None, old_tx_hash=None):
    old_tx_data = old_tx_data or {}

    if not old_tx_hash and not is_gas_need(accumulation_state_id):
        check_balance.apply_async([accumulation_state_id])
        return

    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency
    token = ethereum_manager.get_token_by_symbol(currency)

    token_amount_wei = token.get_base_denomination_balance(address)
    token_amount = token.get_amount_from_base_denomination(token_amount_wei)

    if to_decimal(token_amount) < to_decimal(token.accumulation_min_balance):
        log.warning('Current balance less than minimum, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    # at this point we know amount is enough
    gas_keeper = ethereum_manager.get_gas_keeper_wallet()
    gas_keeper_balance_wei = ethereum_manager.get_balance_in_base_denomination(gas_keeper.address)
    accumulation_gas_amount = token.get_transfer_gas_amount(ETH_SAFE_ADDR, token_amount_wei)
    gas_price = ethereum_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)
    accumulation_gas_total_amount = accumulation_gas_amount * gas_price

    if gas_keeper_balance_wei < accumulation_gas_total_amount:
        log.error('Gas keeper balance too low to send gas: %s',
                  ethereum_manager.get_amount_from_base_denomination(gas_keeper_balance_wei))

    # prepare tx
    if old_tx_data:
        log.info('Gas transaction to %s will be replaced', w3.toChecksumAddress(address))
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        tx_data['value'] = accumulation_gas_total_amount
        if ethereum_manager.get_transaction_receipt(old_tx_hash):
            log.info('Gas TX %s sent. Do not need to replace.')
            return
    else:
        nonce = ethereum_manager.wait_for_nonce(is_gas=True)
        tx_data = {
            'nonce': nonce,
            'gasPrice': gas_price,
            'gas': settings.ETH_TX_GAS,
            'from': w3.toChecksumAddress(gas_keeper.address),
            'to': address,
            'value': accumulation_gas_total_amount,
            'chainId': settings.ETH_CHAIN_ID,
        }

    signed_tx = w3.eth.account.signTransaction(tx_data, gas_keeper.private_key)
    try:
        tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
    except ValueError:
        log.exception('Unable to send accumulation TX')
        ethereum_manager.release_nonce(is_gas=True)
        return

    if not tx_hash:
        log.error('Unable to send accumulation TX')
        ethereum_manager.release_nonce(is_gas=True)
        return

    # TODO uncomment if some txs not appear in etherscan and blockchain
    # time.sleep(1)
    # if not ethereum_manager.web3.eth.getTransaction(tx_hash.hex()):
    #     log.info('Gas tx not found. Resend with higher gas price')
    #     send_gas(accumulation_state_id, old_tx_data=tx_data, old_tx_hash=tx_hash)
    #     return

    # if old_tx_hash:
    #     acc_transaction = AccumulationTransaction.objects.filter(tx_hash=old_tx_hash.hex()).first()
    #     acc_transaction.amount = ethereum_manager.get_eth_amount_from_wei(accumulation_gas_total_amount)
    #     acc_transaction.tx_hash = tx_hash.hex()
    #     acc_transaction.save()
    # else:
    acc_transaction = AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=ethereum_manager.get_amount_from_base_denomination(accumulation_gas_total_amount),
        tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=tx_hash.hex(),
    )
    accumulation_state.state = accumulation_manager.model.STATE_WAITING_FOR_GAS
    accumulation_state.save(update_fields=['state', 'updated'])

    log.info('Gas deposit TX %s sent', tx_hash.hex())

    # wait tx processed
    try:
        ethereum_manager.wait_for_transaction_receipt(tx_hash, poll_latency=3)
        acc_transaction.complete(is_gas=True)
        ethereum_manager.release_nonce(is_gas=True)
        accumulate_erc20.apply_async([accumulation_state.id, True])
    except RetryRequired:
        # retry with higher gas price
        send_gas(accumulation_state_id, old_tx_data=tx_data, old_tx_hash=tx_hash)


@shared_task
def accumulate_eth_dust():
    ethereum_manager.accumulate_dust()
