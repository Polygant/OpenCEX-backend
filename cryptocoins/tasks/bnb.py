import logging
import time

from celery import group, shared_task
from django.conf import settings
from web3 import Web3
from web3.exceptions import BlockNotFound

from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import PENDING as WR_PENDING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.coins.bnb import BNB_CURRENCY
from cryptocoins.coins.bnb.bnb import BnbTransaction, bnb_manager
from cryptocoins.coins.bnb.connection import check_bnb_response_time
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
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal
from lib.notifications import send_telegram_message

log = logging.getLogger(__name__)
accumulation_manager = AccumulationManager()

DEFAULT_BLOCK_ID_DELTA = 1000
w3 = bnb_manager.client
BNB_SAFE_ADDR = w3.toChecksumAddress(settings.BNB_SAFE_ADDR)
BEP20_TOKEN_CURRENCIES = bnb_manager.registered_token_currencies
BEP20_TOKEN_CONTRACT_ADDRESSES = bnb_manager.registered_token_addresses


@shared_task
def bnb_process_new_blocks():
    try:
        current_block_id = w3.eth.blockNumber
    except Exception as e:
        log.exception('Cant get current block')
        w3.change_provider()
        return

    default_block_id = current_block_id - DEFAULT_BLOCK_ID_DELTA
    last_processed_block_id = load_last_processed_block_id(
        currency=BNB_CURRENCY, default=default_block_id
    )

    if last_processed_block_id >= current_block_id:
        log.debug('Nothing to process since block #%s', current_block_id)
        return

    blocks_to_process = list(range(
        last_processed_block_id + 1,
        current_block_id + 1,
    ))
    blocks_to_process.insert(0, last_processed_block_id)

    if len(blocks_to_process) > 1:
        log.info(
            'Need to process blocks #%s..#%s',
            last_processed_block_id + 1,
            current_block_id)
    else:
        log.info('Need to process block #%s', last_processed_block_id + 1)

    # make subtask group
    block_jobs = []

    for block_id in blocks_to_process:
        # block_jobs.append(bnb_process_block.s(block_id))
        bnb_process_block(block_id)

    # jobs_group = group(block_jobs)
    # jobs_group.apply_async()

    store_last_processed_block_id(
        currency=BNB_CURRENCY,
        block_id=current_block_id
    )


@shared_task(bind=True)
def bnb_process_block(self, block_id):
    started_at = time.time()
    log.info('Processing block #%s', block_id)

    try:
        block = w3.eth.getBlock(block_id, full_transactions=True)
        response_time = time.time() - started_at
        check_bnb_response_time(w3, response_time)
    except BlockNotFound as e:
        store_last_processed_block_id(currency=BNB_CURRENCY, block_id=block_id)
        raise e
    except Exception as e:
        log.exception('Cant parse current block')
        store_last_processed_block_id(currency=BNB_CURRENCY, block_id=block_id)
        w3.change_provider()
        raise e

    transactions = block.get('transactions', [])

    if len(transactions) == 0:
        log.info(f'Block #{block_id} has no transactions, skipping')
        return

    log.info(f'Transactions count in block #{block_id}: {len(transactions)}')

    bnb_jobs = []
    bep20_jobs = []

    bnb_withdrawal_requests_pending = get_withdrawal_requests_pending([BNB_CURRENCY])
    bep20_withdrawal_requests_pending = get_withdrawal_requests_pending(BEP20_TOKEN_CURRENCIES, blockchain_currency='BNB')

    bnb_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                            for i in bnb_withdrawal_requests_pending}
    bnb_withdrawal_requests_pending_txs = {v: k for k,
                                           values in bnb_withdrawals_dict.items() for v in values}

    bep20_withdrawals_dict = {i.id: i.data.get('txs_attempts', [])
                              for i in bep20_withdrawal_requests_pending}
    bep20_withdrawal_requests_pending_txs = {
        v: k for k, values in bep20_withdrawals_dict.items() for v in values}

    check_bnb_withdrawal_jobs = []
    check_bep20_withdrawal_jobs = []

    # check for incorrect block response
    valid_txs = [t['to'] for t in transactions if t['to'] != '0x0000000000000000000000000000000000001000']
    if not valid_txs:
        current_provider = w3.provider.endpoint_uri
        w3.change_provider()
        new_provider = w3.provider.endpoint_uri
        msg = f'All txs in block {block_id} are zero.\nChange provider from:\n{current_provider}\nto {new_provider}'
        send_telegram_message(msg)
        raise Exception(f'All txs in block {block_id} are zero')

    # Withdrawals
    for tx_data in transactions:
        tx = BnbTransaction.from_node(tx_data)
        if not tx:
            continue

        # is BNB withdrawal request tx?
        if tx.hash in bnb_withdrawal_requests_pending_txs:
            withdrawal_id = bnb_withdrawal_requests_pending_txs[tx.hash]
            check_bnb_withdrawal_jobs.append(check_tx_withdrawal.s(withdrawal_id, tx.as_dict()))
            continue

        # is BEP20 withdrawal request tx?
        if tx.hash in bep20_withdrawal_requests_pending_txs:
            withdrawal_id = bep20_withdrawal_requests_pending_txs[tx.hash]
            check_bep20_withdrawal_jobs.append(check_tx_withdrawal.s(withdrawal_id, tx.as_dict()))
            continue

    bnb_addresses = set(bnb_manager.get_user_addresses())
    bnb_keeper = bnb_manager.get_keeper_wallet()
    bnb_gas_keeper = bnb_manager.get_gas_keeper_wallet()

    bnb_addresses_deps = set(bnb_addresses)
    bnb_addresses_deps.add(BNB_SAFE_ADDR)

    # Deposits
    for tx_data in transactions:
        tx = BnbTransaction.from_node(tx_data)
        if not tx:
            continue

        if tx.to_addr is None:
            continue

        if tx.to_addr in bnb_addresses_deps:
            # process ETH deposit
            if not tx.contract_address:
                bnb_jobs.append(bnb_process_bnb_deposit.s(tx.as_dict()))
            # process ERC20 deposit
            else:
                bep20_jobs.append(bnb_process_bep20_deposit.s(tx.as_dict()))

    if bnb_jobs:
        log.info(f'Need to check BNB deposits count: {len(bnb_jobs)}')
        group(bnb_jobs).apply_async()

    if bep20_jobs:
        log.info(f'Need to check BEP20 deposits count: {len(bep20_jobs)}', )
        group(bep20_jobs).apply_async()

    if check_bnb_withdrawal_jobs:
        log.info(f'Need to check BNB withdrawals count: {len(check_bnb_withdrawal_jobs)}')
        group(check_bnb_withdrawal_jobs).apply_async()

    if check_bep20_withdrawal_jobs:
        log.info(f'Need to check BEP20 withdrawals count: {len(check_bnb_withdrawal_jobs)}')
        group(check_bep20_withdrawal_jobs).apply_async()

    # check accumulations
    for tx_data in transactions:
        tx = BnbTransaction.from_node(tx_data)
        if not tx:
            continue

        # checks only exchange addresses withdrawals
        if tx.from_addr not in bnb_addresses:
            continue

        # skip txs from keepers
        if tx.from_addr in [bnb_keeper.address, bnb_gas_keeper.address, BNB_SAFE_ADDR]:
            continue

        # checks only if currency flows outside the exchange
        if tx.to_addr in bnb_addresses:
            continue

        # check ERC20 accumulations
        if tx.contract_address:
            token = bnb_manager.get_token_by_address(tx.contract_address)

            accumulation_details, created = AccumulationDetails.objects.get_or_create(
                txid=tx.hash,
                defaults=dict(
                    txid=tx.hash,
                    from_address=tx.from_addr,
                    to_address=tx.to_addr,
                    currency=BNB_CURRENCY,
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
                    currency=BNB_CURRENCY,
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
    log.info('Block #%s processed in %.2f sec. (BNB TX count: %s, BEP20 TX count: %s, WR TX count: %s)',
             block_id, execution_time, len(bnb_jobs), len(bep20_jobs),
             len(check_bep20_withdrawal_jobs) + len(check_bnb_withdrawal_jobs))


@shared_task
def check_tx_withdrawal(withdrawal_id, tx_data):
    tx = BnbTransaction(tx_data)

    withdrawal_request = WithdrawalRequest.objects.filter(
        id=withdrawal_id,
        state=WR_PENDING,
    ).first()

    if withdrawal_request is None:
        log.warning('Invalid withdrawal request state for TX %s', tx.hash)
        return

    withdrawal_request.txid = tx.hash

    if not bnb_manager.is_valid_transaction(tx.hash):
        withdrawal_request.fail()
        return

    withdrawal_request.complete()


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def bnb_process_bnb_deposit(tx_data: dict, deffered=False):
    """
    Process BNB deposit, excepting inner gas deposits, etc
    """
    log.info('Processing bnb deposit: %s', tx_data)
    tx = BnbTransaction(tx_data)
    amount = bnb_manager.get_amount_from_base_denomination(tx.value)

    # skip if failed
    if not bnb_manager.is_valid_transaction(tx.hash):
        log.error(f'BNB deposit transaction {tx.hash} is invalid or failed')
        return

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(amount, 'BNB'):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time('BNB')
        bnb_process_bnb_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    # is accumulation tx?
    if tx.to_addr == BNB_SAFE_ADDR:
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

        log.info(f'Tx {tx.hash} is BNB accumulation')
        return

    bnb_keeper = bnb_manager.get_keeper_wallet()
    bnb_gas_keeper = bnb_manager.get_gas_keeper_wallet()
    # is inner gas deposit?
    if tx.from_addr == bnb_gas_keeper.address:
        accumulation_transaction = AccumulationTransaction.objects.filter(
            tx_hash=tx.hash,
            tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
        ).first()

        if accumulation_transaction is None:
            log.error(f'Gas accumulation TX {tx.hash} not found')
            return

        if accumulation_transaction.tx_state == AccumulationTransaction.STATE_COMPLETED:
            log.info(
                f'Accumulation TX {tx.hash} already processed as token gas')
            return

        log.info(f'Tx {tx.hash} is gas deposit')
        accumulation_transaction.complete(is_gas=True)
        accumulate_bep20.apply_async(
            [accumulation_transaction.accumulation_state.id, True])
        return

    db_wallet = bnb_manager.get_wallet_db_instance(BNB_CURRENCY, tx.to_addr)
    if db_wallet is None:
        log.error(f'Wallet BNB {tx.to_addr} not exists or blocked')
        return

    # is already processed?
    db_wallet_transaction = WalletTransactions.objects.filter(
        tx_hash__iexact=tx.hash,
        wallet_id=db_wallet.id,
    ).first()

    if db_wallet_transaction is not None:
        log.warning('TX %s already processed as BNB deposit', tx.hash)
        return

    # make deposit
    # check for keeper deposit
    if db_wallet.address == bnb_keeper.address:
        log.info('TX %s is keeper BNB deposit: %s', tx.hash, amount)
        return

    # check for gas keeper deposit
    if db_wallet.address == bnb_gas_keeper.address:
        log.info('TX %s is gas keeper BNB deposit: %s', tx.hash, amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(tx.hash, tx.to_addr, amount, BNB_CURRENCY.code)

    if amount < bnb_manager.deposit_min_amount and amount < bnb_manager.accumulation_min_balance:
        log.warning('Deposit %s less than min required, skipping', amount)
        accumulation_manager.set_need_check(db_wallet)
        # accumulate later when amount >= min_dep_limit
        return

    WalletTransactions.objects.create(
        wallet=db_wallet,
        tx_hash=tx.hash,
        amount=amount,
        currency=BNB_CURRENCY,
        state=WalletTransactions.STATE_NOT_CHECKED if is_scoring_ok else WalletTransactions.STATE_BAD_DEPOSIT,
    )
    if is_scoring_ok:
        # set check state
        accumulation_state = accumulation_manager.set_need_check(db_wallet)
        if accumulation_state:
            check_balance.apply_async([accumulation_state.id, True])

        log.info('TX %s processed as %s BNB deposit', tx.hash, amount)
    else:
        log.warning('TX %s processed as %s BNB BAD deposit', tx.hash, amount)


@shared_task(autoretry_for=(RetryRequired,), retry_kwargs={'max_retries': 60})
def bnb_process_bep20_deposit(tx_data: dict, deffered=False):
    """
    Process BEP20 deposit
    """
    log.info('Processing BEP20 deposit: %s', tx_data)
    tx = BnbTransaction(tx_data)

    if not bnb_manager.is_valid_transaction(tx.hash):
        log.warning('BEP20 deposit TX %s is failed or invalid', tx.hash)
        return

    token = bnb_manager.get_token_by_address(tx.contract_address)
    token_to_addr = tx.to_addr
    token_amount = token.get_amount_from_base_denomination(tx.value)

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(token_amount, token.currency.code):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time(token.currency.code)
        bnb_process_bep20_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    if token_to_addr == BNB_SAFE_ADDR:
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

    db_wallet = bnb_manager.get_wallet_db_instance(token.currency, token_to_addr)
    if db_wallet is None:
        log.error('Wallet %s %s not exists or blocked', token.currency, token_to_addr)
        return

    db_wallet_transaction = WalletTransactions.objects.filter(
        tx_hash__iexact=tx.hash,
        wallet_id=db_wallet.id,
    ).first()
    if db_wallet_transaction is not None:
        log.warning(
            'TX %s already processed as %s deposit',
            tx.hash,
            token.currency)
        return

    # check for keeper deposit
    bnb_keeper = bnb_manager.get_keeper_wallet()
    if db_wallet.address == bnb_keeper.address:
        log.info(
            'TX %s is keeper %s deposit: %s',
            tx.hash,
            token.currency,
            token_amount)
        return

    # check for gas keeper deposit
    bnb_gas_keeper = bnb_manager.get_gas_keeper_wallet()
    if db_wallet.address == bnb_gas_keeper.address:
        log.info(
            'TX %s is keeper %s deposit: %s',
            tx.hash,
            token.currency,
            token_amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(
            tx.hash,
            token_to_addr,
            token_amount,
            BNB_CURRENCY.code,
            token.currency.code,
        )

    # process BEP20 deposit
    if token_amount < token.deposit_min_amount and token_amount < token.accumulation_min_balance:
        log.warning(
            'Deposit %s %s less than min required, skipping',
            token.currency,
            token_amount)
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

        log.info('TX %s processed as %s %s deposit',
                 tx.hash, token_amount, token.currency)
    else:
        log.warning('TX %s processed as %s %s BAD deposit', tx.hash, token_amount, token.currency.code)


@shared_task
def process_payouts(password):
    bnb_withdrawal_requests = get_withdrawal_requests_to_process(currencies=[
        BNB_CURRENCY])

    jobs_list = []

    if bnb_withdrawal_requests:
        log.info(
            'Need to process %s BNB withdrawals',
            len(bnb_withdrawal_requests))

        for item in bnb_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            withdraw_bnb.apply_async([item.id, password])

    bep20_withdrawal_requests = get_withdrawal_requests_to_process(
        currencies=BEP20_TOKEN_CURRENCIES,
        blockchain_currency='BNB'
    )

    if bep20_withdrawal_requests:
        log.info(
            'Need to process %s BEP20 withdrawals',
            len(bep20_withdrawal_requests))
        for item in bep20_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            withdraw_bep20.apply_async([item.id, password])


@shared_task
def withdraw_bnb(withdrawal_request_id, password,
                 old_tx_data=None, prev_tx_hash=None):
    if old_tx_data is None:
        old_tx_data = {}
    withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

    # todo: handle errors
    address = w3.toChecksumAddress(withdrawal_request.data.get('destination'))
    keeper = bnb_manager.get_keeper_wallet()
    amount_wei = bnb_manager.get_base_denomination_from_amount(withdrawal_request.amount)
    withdrawal_fee_wei = Web3.toWei(to_decimal(
        get_withdrawal_fee(BNB_CURRENCY, BNB_CURRENCY)), 'ether')
    amount_to_send_wei = amount_wei - withdrawal_fee_wei

    gas_price = bnb_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)

    # todo: check min limit
    if amount_to_send_wei <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    keeper_balance = bnb_manager.get_balance_in_base_denomination(keeper.address)
    if keeper_balance < (amount_to_send_wei +
                         (gas_price * settings.BNB_TX_GAS)):
        log.warning('Keeper not enough BNB, skipping')
        return

    if old_tx_data:
        log.info(
            'BNB withdrawal transaction to %s will be replaced',
            w3.toChecksumAddress(address))
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        if prev_tx_hash and bnb_manager.get_transaction_receipt(prev_tx_hash):
            log.info('BNB TX %s sent. Do not need to replace.')
            return
    else:
        nonce = bnb_manager.wait_for_nonce()
        tx_data = {
            'nonce': nonce,
            'gasPrice': gas_price,
            'gas': settings.BNB_TX_GAS,
            'from': w3.toChecksumAddress(keeper.address),
            'to': w3.toChecksumAddress(address),
            'value': amount_to_send_wei,
            'chainId': settings.BNB_CHAIN_ID,
        }

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

    tx_hash = bnb_manager.send_tx(
        private_key=private_key,
        to_address=address,
        amount=amount_to_send_wei,
        nonce=tx_data['nonce'],
        gasPrice=tx_data['gasPrice'],
    )

    if not tx_hash:
        log.error('Unable to send withdrawal TX')
        bnb_manager.release_nonce()
        return

    withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
    withdrawal_txs_attempts.append(tx_hash.hex())

    withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))

    withdrawal_request.state = WR_PENDING
    withdrawal_request.our_fee_amount = bnb_manager.get_amount_from_base_denomination(withdrawal_fee_wei)
    withdrawal_request.save(update_fields=['state', 'updated', 'our_fee_amount', 'data'])
    log.info('BNB withdrawal TX %s sent', tx_hash.hex())

    # wait tx processed
    try:
        bnb_manager.wait_for_transaction_receipt(tx_hash, poll_latency=2)
        bnb_manager.release_nonce()
    except RetryRequired:
        # retry with higher gas price
        withdraw_bnb(
            withdrawal_request_id,
            password,
            old_tx_data=tx_data,
            prev_tx_hash=tx_hash)


@shared_task
def withdraw_bep20(withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
    if old_tx_data is None:
        old_tx_data = {}

    withdrawal_request = WithdrawalRequest.objects.get(
        id=withdrawal_request_id)

    address = w3.toChecksumAddress(withdrawal_request.data.get('destination'))
    currency = withdrawal_request.currency

    token = bnb_manager.get_token_by_symbol(currency)
    send_amount_wei = token.get_base_denomination_from_amount(withdrawal_request.amount)
    withdrawal_fee_wei = token.get_base_denomination_from_amount(token.withdrawal_fee)
    amount_to_send_wei = send_amount_wei - withdrawal_fee_wei
    if amount_to_send_wei <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    gas_price = bnb_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)

    transfer_gas = token.get_transfer_gas_amount(
        address, amount_to_send_wei, True)

    keeper = bnb_manager.get_keeper_wallet()
    keeper_bnb_balance = bnb_manager.get_balance_in_base_denomination(keeper.address)
    keeper_token_balance = token.get_base_denomination_balance(keeper.address)

    if keeper_bnb_balance < gas_price * transfer_gas:
        log.warning('Keeper not enough BNB for gas, skipping')
        return

    if keeper_token_balance < amount_to_send_wei:
        log.warning('Keeper not enough %s, skipping', currency)
        return

    log.info('Amount to send: %s, gas price: %s, transfer gas: %s',
             amount_to_send_wei, gas_price, transfer_gas)

    if old_tx_data:
        log.info(
            '%s withdrawal to %s will be replaced',
            currency.code,
            address)
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        if prev_tx_hash and bnb_manager.get_transaction_receipt(prev_tx_hash):
            log.info('Token TX %s sent. Do not need to replace.')
            return
    else:
        nonce = bnb_manager.wait_for_nonce()
        tx_data = {
            'chainId': settings.BNB_CHAIN_ID,
            'gas': transfer_gas,
            'gasPrice': gas_price,
            'nonce': nonce,
        }

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)
    tx_hash = token.send_token(private_key, address, amount_to_send_wei, **tx_data)

    if not tx_hash:
        log.error('Unable to send token withdrawal TX')
        bnb_manager.release_nonce()
        return

    withdrawal_txs_attempts = withdrawal_request.data.get('txs_attempts', [])
    withdrawal_txs_attempts.append(tx_hash.hex())

    withdrawal_request.data['txs_attempts'] = list(set(withdrawal_txs_attempts))
    withdrawal_request.state = WR_PENDING
    withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(
        withdrawal_fee_wei)

    withdrawal_request.save(
        update_fields=[
            'state',
            'updated',
            'our_fee_amount',
            'data'])
    log.info('%s withdrawal TX %s sent', currency, tx_hash.hex())

    # wait tx processed
    try:
        bnb_manager.wait_for_transaction_receipt(tx_hash, poll_latency=2)
        bnb_manager.release_nonce()
    except RetryRequired:
        # retry with higher gas price
        withdraw_bep20(
            withdrawal_request_id,
            password,
            old_tx_data=tx_data,
            prev_tx_hash=tx_hash)


@shared_task
def check_balances():
    jobs_list = []

    for item in accumulation_manager.get_waiting_for_check(blockchain_currency=BNB_CURRENCY):
        jobs_list.append(check_balance.s(item.id))

    for item in accumulation_manager.get_stuck(blockchain_currency=BNB_CURRENCY):
        jobs_list.append(check_balance.s(item.id))

    if jobs_list:
        log.info('Need to check count: %s', len(jobs_list))
        jobs_group = group(jobs_list)
        jobs_group.apply_async()


def is_gas_need(accumulation_state_id):
    acc_tx = accumulation_manager.get_last_gas_deposit_tx(
        accumulation_state_id)
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

    # BNB
    if currency == BNB_CURRENCY:
        log.info('Checking BNB %s balance', address)
        amb = bnb_manager.accumulation_min_balance
        if not instant:
            amount_wei = bnb_manager.get_balance_in_base_denomination(address)
            amount = bnb_manager.get_amount_from_base_denomination(amount_wei)
            accumulation_state.current_balance = amount
            log.info('Current BNB balance of %s is %s; Min accumulation amount is %s',
                     address, amount, amb)

            if not amount or amount < amb:
                log.info(
                    'Low balance of %s %s (current %s)',
                    currency,
                    address,
                    amb)
                accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
                accumulation_state.save(
                    update_fields=[
                        'current_balance',
                        'state',
                        'updated'])
                return

        else:
            log.info(f'Try to accumulate BNB instant for {address}')
            accumulation_state.state = accumulation_manager.model.STATE_READY_FOR_ACCUMULATION
            accumulation_state.save(
                update_fields=[
                    'current_balance',
                    'state',
                    'updated'])

        accumulate_bnb.apply_async([accumulation_state.id, instant])

    # tokens
    else:
        log.info('Checking %s %s balance', currency, address)
        token = bnb_manager.get_token_by_symbol(currency)
        if not instant:
            amount = token.get_balance(address)
            log.info('Balance of %s %s is %s; Min accumulation amount is %s',
                     currency, address, amount, token.accumulation_min_balance)

            accumulation_state.current_balance = amount

            # check min accumulation amount
            if not amount or amount < token.accumulation_min_balance:
                log.info(f'Low balance of {currency} {address}')
                accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
                accumulation_state.save(
                    update_fields=[
                        'current_balance',
                        'state',
                        'updated'])
                return

        if not is_gas_need(accumulation_state_id):
            log.info(f'Gas not required for {currency} {address}')
            accumulation_state.state = accumulation_manager.model.STATE_READY_FOR_ACCUMULATION
            accumulation_state.save(
                update_fields=[
                    'current_balance',
                    'state',
                    'updated'])
            accumulate_bep20.apply_async([accumulation_state.id, instant])
            log.info(f'{address} balance checked')
        else:
            log.info(f'Gas required for {currency} {address}')
            accumulation_state.state = accumulation_manager.model.STATE_GAS_REQUIRED
            accumulation_state.save(
                update_fields=[
                    'current_balance',
                    'state',
                    'updated'])
            send_gas.apply_async([accumulation_state.id])

    log.info(f'{address} balance checked')


@shared_task
def accumulate_bnb(accumulation_state_id, instant=False):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address

    # recheck balance
    if instant:
        amount_wei = bnb_manager.wait_for_balance_in_base_denomination(address)
    else:
        amount_wei = bnb_manager.get_balance_in_base_denomination(address)

    amount = bnb_manager.get_amount_from_base_denomination(amount_wei)
    log.info('Accumulation BNB from: %s; Balance: %s; Min acc balance:%s',
             address, amount, bnb_manager.accumulation_min_balance)

    if not amount:
        log.warning('Current balance is 0 BNB. Need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    if amount < bnb_manager.accumulation_min_balance:
        log.warning('Current balance less than minimum, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    accumulation_address = bnb_manager.get_accumulation_address(amount)

    # we want to process our tx faster
    gas_price = bnb_manager.gas_price_cache.get_increased_price()
    gas_amount = gas_price * settings.BNB_TX_GAS
    withdrawal_amount = amount_wei - gas_amount

    # in debug mode values can be very small
    if withdrawal_amount <= 0:
        log.error('BNB withdrawal amount invalid: %s',
                  bnb_manager.get_amount_from_base_denomination(withdrawal_amount))
        accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
        accumulation_state.save(update_fields=['state', 'updated'])
        return

    # prepare tx
    wallet = bnb_manager.get_user_wallet('BNB', address)
    nonce = bnb_manager.client.eth.getTransactionCount(address)

    tx_hash = bnb_manager.send_tx(
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
        amount=bnb_manager.get_amount_from_base_denomination(withdrawal_amount),
        tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=tx_hash.hex(),
    )

    accumulation_state.state = accumulation_manager.model.STATE_ACCUMULATION_IN_PROCESS
    accumulation_state.save(update_fields=['state', 'updated'])

    # create details for alert reason
    AccumulationDetails.objects.create(
        currency=BNB_CURRENCY,
        txid=tx_hash.hex(),
        from_address=address,
        to_address=accumulation_address
    )

    log.info(f'Accumulation TX {tx_hash.hex()} sent from {wallet.address} to {accumulation_address}')


@shared_task
def accumulate_bep20(accumulation_state_id, instant=False):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency

    gas_deposit_tx = accumulation_manager.get_last_gas_deposit_tx(
        accumulation_state_id)
    if gas_deposit_tx is None:
        log.warning(f'Gas deposit for {address} not found or in process')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    token = bnb_manager.get_token_by_symbol(currency)
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

    log.info(
        f'Accumulation {currency} from: {address}; Balance: {token_amount};')

    # if token_amount_wei < checked_amount_wei:
    #     log.warning('Token amount less than last checked, need to recheck')
    #     accumulation_manager.set_need_check(accumulation_state.wallet)
    #     return

    accumulation_gas_amount = bnb_manager.get_base_denomination_from_amount(
        gas_deposit_tx.amount)
    bnb_amount_wei = bnb_manager.get_balance_in_base_denomination(address)

    if bnb_amount_wei < accumulation_gas_amount:
        log.warning(f'Wallet BNB amount: {bnb_amount_wei} less than gas needed '
                    f'{accumulation_gas_amount}, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    accumulation_gas_required_amount = token.get_transfer_gas_amount(
        accumulation_address,
        token_amount_wei,
    )

    # calculate from existing wallet eth amount
    gas_price = int(accumulation_gas_amount / accumulation_gas_required_amount)

    wallet = bnb_manager.get_user_wallet(currency, address)
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

    # create details for alert reason
    AccumulationDetails.objects.create(
        currency=BNB_CURRENCY,
        txid=tx_hash.hex(),
        from_address=address,
        to_address=accumulation_address
    )

    log.info(f'Token accumulation TX {tx_hash.hex()} sent from {wallet.address} to: {accumulation_address}')


@shared_task
def send_gas(accumulation_state_id, old_tx_data=None, old_tx_hash=None):
    old_tx_data = old_tx_data or {}

    if not old_tx_hash and not is_gas_need(accumulation_state_id):
        check_balance.apply_async([accumulation_state_id])
        return

    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency
    token = bnb_manager.get_token_by_symbol(currency)

    token_amount_wei = token.get_base_denomination_balance(address)
    token_amount = token.get_amount_from_base_denomination(token_amount_wei)

    if to_decimal(token_amount) < to_decimal(token.accumulation_min_balance):
        log.warning('Current balance less than minimum, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    # at this point we know amount is enough
    gas_keeper = bnb_manager.get_gas_keeper_wallet()
    gas_keeper_balance_wei = bnb_manager.get_balance_in_base_denomination(
        gas_keeper.address)
    accumulation_gas_amount = token.get_transfer_gas_amount(
        BNB_SAFE_ADDR, token_amount_wei)
    gas_price = bnb_manager.gas_price_cache.get_increased_price(
        old_tx_data.get('gasPrice') or 0)
    accumulation_gas_total_amount = accumulation_gas_amount * gas_price

    if gas_keeper_balance_wei < accumulation_gas_total_amount:
        log.error('Gas keeper balance too low to send gas: %s',
                  bnb_manager.get_amount_from_base_denomination(gas_keeper_balance_wei))

    # prepare tx
    if old_tx_data:
        log.info(f'Gas transaction to {address} will be replaced')
        tx_data = old_tx_data.copy()
        tx_data['gasPrice'] = gas_price
        tx_data['value'] = accumulation_gas_total_amount
        if bnb_manager.get_transaction_receipt(old_tx_hash):
            log.info(f'Gas TX {old_tx_hash} sent. Do not need to replace.')
            return
    else:
        nonce = bnb_manager.wait_for_nonce(is_gas=True)
        tx_data = {
            'nonce': nonce,
            'gasPrice': gas_price,
            'gas': settings.BNB_TX_GAS,
            'from': w3.toChecksumAddress(gas_keeper.address),
            'to': address,
            'value': accumulation_gas_total_amount,
            'chainId': settings.BNB_CHAIN_ID,
        }

    signed_tx = w3.eth.account.signTransaction(tx_data, gas_keeper.private_key)
    try:
        tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
    except ValueError:
        log.exception('Unable to send accumulation TX')
        bnb_manager.release_nonce(is_gas=True)
        return

    if not tx_hash:
        log.error('Unable to send accumulation TX')
        bnb_manager.release_nonce(is_gas=True)
        return

    # TODO uncomment if some txs not appear in etherscan and blockchain
    # time.sleep(1)
    # if not bnb_manager.web3.eth.getTransaction(tx_hash.hex()):
    #     log.info('Gas tx not found. Resend with higher gas price')
    #     send_gas(accumulation_state_id, old_tx_data=tx_data, old_tx_hash=tx_hash)
    #     return

    # if old_tx_hash:
    #     acc_transaction = AccumulationTransaction.objects.filter(tx_hash=old_tx_hash.hex()).first()
    #     acc_transaction.amount = bnb_manager.get_eth_amount_from_wei(accumulation_gas_total_amount)
    #     acc_transaction.tx_hash = tx_hash.hex()
    #     acc_transaction.save()
    # else:
    acc_transaction = AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=bnb_manager.get_amount_from_base_denomination(
            accumulation_gas_total_amount),
        tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=tx_hash.hex(),
    )
    accumulation_state.state = accumulation_manager.model.STATE_WAITING_FOR_GAS
    accumulation_state.save(update_fields=['state', 'updated'])

    log.info('Gas deposit TX %s sent', tx_hash.hex())

    # wait tx processed
    try:
        bnb_manager.wait_for_transaction_receipt(tx_hash, poll_latency=3)
        acc_transaction.complete(is_gas=True)
        bnb_manager.release_nonce(is_gas=True)
        accumulate_bep20.apply_async([accumulation_state.id, True])
    except RetryRequired:
        # retry with higher gas price
        send_gas(
            accumulation_state_id,
            old_tx_data=tx_data,
            old_tx_hash=tx_hash)


@shared_task
def accumulate_bnb_dust():
    bnb_manager.accumulate_dust()