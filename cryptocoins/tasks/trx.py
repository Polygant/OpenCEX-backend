import logging
import time

from celery import group, shared_task
from django.conf import settings

from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import PENDING as WR_PENDING
from core.models.inouts.withdrawal import WithdrawalRequest
from core.utils.inouts import get_withdrawal_fee
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.coins.trx import TRX_CURRENCY
from cryptocoins.coins.trx.tron import TrxTransaction, tron_manager
from cryptocoins.coins.trx.tron import tron_client
from cryptocoins.models import AccumulationDetails, ScoringSettings
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
from lib.utils import memcache_lock

log = logging.getLogger(__name__)

accumulation_manager = AccumulationManager()

DEFAULT_BLOCK_ID_DELTA = 1000
TRX_SAFE_ADDR = settings.TRX_SAFE_ADDR
TRX_NET_FEE = settings.TRX_NET_FEE
TRC20_FEE_LIMIT = settings.TRC20_FEE_LIMIT
TRC20_TOKEN_CURRENCIES = tron_manager.registered_token_currencies
TRC20_TOKEN_CONTRACT_ADDRESSES = tron_manager.registered_token_addresses


@shared_task
def trx_process_new_blocks():
    lock_id = 'trx_blocks'
    with memcache_lock(lock_id, lock_id) as acquired:
        if acquired:
            current_block_id = tron_client.get_latest_block_number()
            default_block_id = current_block_id - DEFAULT_BLOCK_ID_DELTA
            last_processed_block_id = load_last_processed_block_id(
                currency=TRX_CURRENCY, default=default_block_id)

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

            for block_id in blocks_to_process:
                trx_process_block(block_id)

            store_last_processed_block_id(currency=TRX_CURRENCY, block_id=current_block_id)


@shared_task(bind=True)
def trx_process_block(self, block_id):
    started_at = time.time()
    time.sleep(0.1)
    log.info('Processing block #%s', block_id)

    try:
        block = tron_client.get_block(block_id)
    except Exception as e:
        store_last_processed_block_id(currency=TRX_CURRENCY, block_id=block_id - 1)
        raise e

    transactions = block.get('transactions', [])

    if not transactions:
        log.info('Block #%s has no transactions, skipping', block_id)
        return

    log.info('Transactions count in block #%s: %s', block_id, len(transactions))

    trx_jobs = []
    trc20_jobs = []

    trx_withdrawal_requests_pending = get_withdrawal_requests_pending([TRX_CURRENCY])
    trc20_withdrawal_requests_pending = get_withdrawal_requests_pending(TRC20_TOKEN_CURRENCIES, blockchain_currency='TRX')

    trx_withdrawal_requests_pending_txs = [i.txid for i in trx_withdrawal_requests_pending]
    trc20_withdrawal_requests_pending_txs = [i.txid for i in trc20_withdrawal_requests_pending]

    check_trx_withdrawal_jobs = []
    check_trc20_withdrawal_jobs = []

    all_valid_transactions = []
    for tx_data in transactions:
        tx: TrxTransaction = TrxTransaction.from_node(tx_data)
        if tx:
            all_valid_transactions.append(tx)

    # Withdrawals
    for tx in all_valid_transactions:
        # is TRX withdrawal request tx?
        if tx.hash in trx_withdrawal_requests_pending_txs:
            check_trx_withdrawal_jobs.append(check_tx_withdrawal.s(tx.as_dict()))
            continue

        # is TRC20 withdrawal request tx?
        if tx.hash in trc20_withdrawal_requests_pending_txs:
            check_trc20_withdrawal_jobs.append(check_tx_withdrawal.s(tx.as_dict()))
            continue

    keeper_wallet = tron_manager.get_keeper_wallet()
    gas_keeper_wallet = tron_manager.get_keeper_wallet()
    trx_addresses = set(tron_manager.get_user_addresses())

    trx_addresses_deps = set(trx_addresses)
    trx_addresses_deps.add(TRX_SAFE_ADDR)

    # Deposits
    for tx in all_valid_transactions:
        # process TRX deposit

        if tx.to_addr in trx_addresses_deps:
            # Process TRX
            if not tx.contract_address:
                trx_jobs.append(trx_process_trx_deposit.s(tx.as_dict()))
            # Process TRC20
            elif tx.contract_address and tx.contract_address in TRC20_TOKEN_CONTRACT_ADDRESSES:
                trc20_jobs.append(trx_process_trc20_deposit.s(tx.as_dict()))

    # Accumulations monitoring
    for tx in all_valid_transactions:
        if tx.from_addr in trx_addresses and tx.to_addr not in trx_addresses:

            # skip keepers withdrawals
            if tx.from_addr in [keeper_wallet.address, gas_keeper_wallet.address]:
                continue

            accumulation_details = AccumulationDetails.objects.filter(
                txid=tx.hash
            ).first()

            if accumulation_details:
                log.info(f'Accumulation details for {tx.hash} already exists')
                continue

            accumulation_details = {
                'currency': TRX_CURRENCY,
                'txid': tx.hash,
                'from_address': tx.from_addr,
                'to_address': tx.to_addr,
                'state': AccumulationDetails.STATE_COMPLETED
            }

            if not tx.contract_address:
                # Store TRX accumulations
                AccumulationDetails.objects.create(**accumulation_details)

            elif tx.contract_address and tx.contract_address in TRC20_TOKEN_CONTRACT_ADDRESSES:
                # Store TRC20 accumulations
                token = tron_manager.get_token_by_address(tx.contract_address)
                accumulation_details['token_currency'] = token.currency
                AccumulationDetails.objects.create(**accumulation_details)

    if trx_jobs:
        log.info('Need to check TRX deposits count: %s', len(trx_jobs))
        group(trx_jobs).apply_async()

    if trc20_jobs:
        log.info('Need to check TRC20 withdrawals count: %s', len(trc20_jobs))
        group(trc20_jobs).apply_async()

    if check_trx_withdrawal_jobs:
        log.info('Need to check TRX withdrawals count: %s', len(check_trx_withdrawal_jobs))
        group(check_trx_withdrawal_jobs).apply_async()

    if check_trc20_withdrawal_jobs:
        log.info('Need to check TRC20 withdrawals count: %s', len(check_trx_withdrawal_jobs))
        group(check_trc20_withdrawal_jobs).apply_async()

    execution_time = time.time() - started_at
    log.info('Block #%s processed in %.2f sec. (TRX TX count: %s, TRC20 TX count: %s, WR TX count: %s)',
             block_id, execution_time, len(trx_jobs), len(trc20_jobs),
             len(check_trc20_withdrawal_jobs) + len(check_trx_withdrawal_jobs))


@shared_task
def check_tx_withdrawal(tx_data):
    tx = TrxTransaction(tx_data)
    withdrawal_request = WithdrawalRequest.objects.filter(
        txid=tx.hash,
        state=WR_PENDING,
    ).first()

    if withdrawal_request is None:
        log.warning('Invalid withdrawal request state for TX %s', tx.hash)
        return

    transaction = tron_client.get_transaction(tx.hash)
    if transaction['ret'][0]['contractRet'] != 'SUCCESS':
        withdrawal_request.fail()
    else:
        withdrawal_request.complete()


@shared_task
def trx_process_trx_deposit(tx_data: dict, deffered=False):
    """
    Process TRX deposit, excepting inner gas deposits, etc
    """
    log.info('Processing TRX deposit: %s', tx_data)
    tx = TrxTransaction(tx_data)
    amount = tron_manager.get_amount_from_base_denomination(tx.value)

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(amount, 'TRX'):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time('TRX')
        trx_process_trx_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    # is accumulation tx?
    if tx.to_addr == TRX_SAFE_ADDR:
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

        log.info(f'Tx {tx.hash} is TRX accumulation')
        return

    trx_keeper = tron_manager.get_keeper_wallet()
    trx_gas_keeper = tron_manager.get_gas_keeper_wallet()
    # is inner gas deposit?
    if tx.from_addr == trx_gas_keeper.address:
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
        accumulate_trc20.apply_async([accumulation_transaction.accumulation_state.id])
        return

    db_wallet = tron_manager.get_wallet_db_instance(TRX_CURRENCY, tx.to_addr)
    if db_wallet is None:
        log.error(f'Wallet TRX {tx.to_addr} not exists or blocked')
        return

    # is already processed?
    db_wallet_transaction = WalletTransactions.objects.filter(
        tx_hash__iexact=tx.hash,
        wallet_id=db_wallet.id,
    ).first()

    if db_wallet_transaction is not None:
        log.warning('TX %s already processed as TRX deposit', tx.hash)
        return

    # make deposit
    # check for keeper deposit
    if db_wallet.address == trx_keeper.address:
        log.info('TX %s is keeper TRX deposit: %s', tx.hash, amount)
        return

    # check for gas keeper deposit
    if db_wallet.address == trx_gas_keeper.address:
        log.info('TX %s is gas keeper TRX deposit: %s', tx.hash, amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(tx.hash, tx.to_addr, amount, TRX_CURRENCY.code)

    if amount < tron_manager.deposit_min_amount and amount < tron_manager.accumulation_min_balance:
        log.warning('Deposit %s less than min required, skipping', amount)
        accumulation_manager.set_need_check(db_wallet)
        # accumulate later when amount >= min_dep_limit
        return

    WalletTransactions.objects.create(
        wallet=db_wallet,
        tx_hash=tx.hash,
        amount=amount,
        currency=TRX_CURRENCY,
        state=WalletTransactions.STATE_NOT_CHECKED if is_scoring_ok else WalletTransactions.STATE_BAD_DEPOSIT,
    )
    if is_scoring_ok:
        # set check state
        accumulation_state = accumulation_manager.set_need_check(db_wallet)
        if accumulation_state:
            check_balance.apply_async([accumulation_state.id])

        log.info('TX %s processed as %s TRX deposit', tx.hash, amount)
    else:
        log.warning('TX %s processed as %s TRX BAD deposit', tx.hash, amount)


@shared_task
def trx_process_trc20_deposit(tx_data: dict, deffered=False):
    """
    Process TRC20 deposit
    """
    log.info('Processing TRC20 deposit: %s', tx_data)
    tx = TrxTransaction(tx_data)

    token = tron_manager.get_token_by_address(tx.contract_address)
    token_to_addr = tx.to_addr
    token_amount = token.get_amount_from_base_denomination(tx.value)

    # check tx scoring
    if not deffered and ScoringSettings.need_to_check_score(token_amount, token.currency.code):
        log.info(f'Need to check scoring for {tx_data}')
        defer_time = ScoringSettings.get_deffered_scoring_time(token.currency.code)
        trx_process_trc20_deposit.apply_async([tx_data, True], countdown=defer_time)
        return

    if token_to_addr == TRX_SAFE_ADDR:
        log.info('TX %s is %s %s accumulation', tx.hash, token_amount, token.currency)

        accumulation_transaction = AccumulationTransaction.objects.filter(
            tx_hash=tx.hash,
        ).first()
        if accumulation_transaction is None:
            # accumulation from outside
            log.error('Token accumulation TX %s not exist', tx.hash)
            return

        accumulation_transaction.complete()
        return

    db_wallet = tron_manager.get_wallet_db_instance(token.currency, token_to_addr)
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
    trx_keeper = tron_manager.get_keeper_wallet()
    if db_wallet.address == trx_keeper.address:
        log.info('TX %s is keeper %s deposit: %s', tx.hash, token.currency, token_amount)
        return

    # check for gas keeper deposit
    trx_gas_keeper = tron_manager.get_gas_keeper_wallet()
    if db_wallet.address == trx_gas_keeper.address:
        log.info('TX %s is keeper %s deposit: %s', tx.hash, token.currency, token_amount)
        return

    is_scoring_ok = True
    if deffered:
        is_scoring_ok = ScoreManager.is_address_scoring_ok(
            tx.hash,
            token_to_addr,
            token_amount,
            TRX_CURRENCY.code,
            token.currency.code
        )

    # process TRC20 deposit
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
            check_balance.apply_async([accumulation_state.id])

        log.info('TX %s processed as %s %s deposit', tx.hash, token_amount, token.currency)
    else:
        log.warning('TX %s processed as %s %s BAD deposit', tx.hash, token_amount, token.currency.code)


@shared_task
def process_payouts(password):
    trx_withdrawal_requests = get_withdrawal_requests_to_process(currencies=[TRX_CURRENCY])

    if trx_withdrawal_requests:
        log.info('Need to process %s TRX withdrawals', len(trx_withdrawal_requests))
        jobs_list = []
        for item in trx_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            jobs_list.append(withdraw_trx.s(item.id, password))

        group(jobs_list).apply()

    erc20_withdrawal_requests = get_withdrawal_requests_to_process(
        currencies=TRC20_TOKEN_CURRENCIES,
        blockchain_currency='TRX'
    )

    if erc20_withdrawal_requests:
        log.info('Need to process %s ERC20 withdrawals', len(erc20_withdrawal_requests))
        jobs_list = []
        for item in erc20_withdrawal_requests:
            # skip freezed withdrawals
            if item.user.profile.is_payouts_freezed():
                continue
            jobs_list.append(withdraw_trc20.s(item.id, password))

        group(jobs_list).apply()


@shared_task
def withdraw_trx(withdrawal_request_id, password):
    withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

    address = withdrawal_request.data.get('destination')
    keeper = tron_manager.get_keeper_wallet()
    amount_sun = tron_manager.get_base_denomination_from_amount(withdrawal_request.amount)

    withdrawal_fee_sun = tron_manager.get_base_denomination_from_amount(
        to_decimal(get_withdrawal_fee(TRX_CURRENCY, TRX_CURRENCY)))
    amount_to_send_sun = amount_sun - withdrawal_fee_sun

    # todo: check min limit
    if amount_to_send_sun <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    if amount_to_send_sun - TRX_NET_FEE < 0:
        log.error('Keeper balance too low')
        return

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

    res = tron_manager.send_tx(private_key, address, amount_to_send_sun)
    txid = res.get('txid')

    if not res.get('result') or not txid:
        log.error('Unable to send withdrawal TX')

    withdrawal_request.state = WR_PENDING
    withdrawal_request.txid = txid
    withdrawal_request.our_fee_amount = tron_manager.get_amount_from_base_denomination(withdrawal_fee_sun)
    withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])
    receipt = res.wait()
    log.info(receipt)
    log.info('TRX withdrawal TX %s sent', txid)


@shared_task
def withdraw_trc20(withdrawal_request_id, password):
    withdrawal_request = WithdrawalRequest.objects.get(id=withdrawal_request_id)

    address = withdrawal_request.data.get('destination')
    currency = withdrawal_request.currency

    token = tron_manager.get_token_by_symbol(currency)
    send_amount_sun = token.get_base_denomination_from_amount(withdrawal_request.amount)
    withdrawal_fee_sun = token.get_base_denomination_from_amount(token.withdrawal_fee)
    amount_to_send_sun = send_amount_sun - withdrawal_fee_sun

    if amount_to_send_sun <= 0:
        log.error('Invalid withdrawal amount')
        withdrawal_request.fail()
        return

    keeper = tron_manager.get_keeper_wallet()
    keeper_trx_balance = tron_manager.get_balance_in_base_denomination(keeper.address)
    keeper_token_balance = token.get_base_denomination_balance(keeper.address)

    if keeper_trx_balance < TRX_NET_FEE:
        log.warning('Keeper not enough TRX, skipping')
        return

    if keeper_token_balance < amount_to_send_sun:
        log.warning('Keeper not enough %s, skipping', currency)
        return

    private_key = AESCoderDecoder(password).decrypt(keeper.private_key)

    res = token.send_token(private_key, address, amount_to_send_sun)
    txid = res.get('txid')

    if not res.get('result') or not txid:
        log.error('Unable to send TRX TX')

    withdrawal_request.state = WR_PENDING
    withdrawal_request.txid = txid
    withdrawal_request.our_fee_amount = token.get_amount_from_base_denomination(withdrawal_fee_sun)
    withdrawal_request.save(update_fields=['state', 'txid', 'updated', 'our_fee_amount'])
    receipt = res.wait()
    log.info(receipt)
    log.info('%s withdrawal TX %s sent', currency, txid)


@shared_task
def check_balances():
    jobs_list = []

    for item in accumulation_manager.get_waiting_for_check(blockchain_currency=TRX_CURRENCY):
        if tron_manager.is_valid_address(item.wallet.address):
            jobs_list.append(check_balance.s(item.id))

    for item in accumulation_manager.get_stuck(blockchain_currency=TRX_CURRENCY):
        if tron_manager.is_valid_address(item.wallet.address):
            jobs_list.append(check_balance.s(item.id))

    if jobs_list:
        log.info('Need to check count: %s', len(jobs_list))
        jobs_group = group(jobs_list)
        jobs_group.apply_async()


@shared_task
def check_balance(accumulation_state_id):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency

    # TRX
    if currency == TRX_CURRENCY:
        log.info('Checking TRX %s balance', address)

        amb = tron_manager.accumulation_min_balance
        amount_sun = tron_manager.get_balance_in_base_denomination(address)
        amount = tron_manager.get_amount_from_base_denomination(amount_sun)
        accumulation_state.current_balance = amount
        log.info('Current TRX balance of %s is %s; Min accumulation amount is %s', address, amount, amb)

        if not amount or amount < amb:
            log.info('Low balance of %s %s (current %s)', currency, address, amb)
            accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
            accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])
            return

        accumulate_trx.apply_async([accumulation_state.id])

    # tokens
    else:
        log.info('Checking %s %s balance', currency, address)
        token = tron_manager.get_token_by_symbol(currency)
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

        accumulation_state.state = accumulation_manager.model.STATE_READY_FOR_ACCUMULATION
        accumulation_state.save(update_fields=['current_balance', 'state', 'updated'])

        accumulate_trc20.apply_async([accumulation_state.id])

    log.info(f'{address} balance checked')


@shared_task
def accumulate_trx(accumulation_state_id):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address

    amount_sun = tron_manager.get_balance_in_base_denomination(address)

    amount = tron_manager.get_amount_from_base_denomination(amount_sun)
    log.info('Accumulation TRX from: %s; Balance: %s; Min acc balance:%s',
             address, amount, tron_manager.accumulation_min_balance)

    if not amount:
        log.warning('Current balance is 0 TRX. Need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    if amount < tron_manager.accumulation_min_balance:
        log.warning('Current balance less than minimum, need to recheck')
        accumulation_manager.set_need_check(accumulation_state.wallet)
        return

    # minus coins to be burnt
    withdrawal_amount = amount_sun - TRX_NET_FEE

    # in debug mode values can be very small
    if withdrawal_amount <= 0:
        log.error('TRX withdrawal amount invalid: %s',
                  tron_manager.get_amount_from_base_denomination(withdrawal_amount))
        accumulation_state.state = accumulation_manager.model.STATE_LOW_BALANCE
        accumulation_state.save(update_fields=['state', 'updated'])
        return

    # prepare tx
    wallet = tron_manager.get_user_wallet('TRX', address)

    res = tron_manager.send_tx(wallet.private_key, TRX_SAFE_ADDR, withdrawal_amount)
    txid = res.get('txid')

    if not res.get('result') or not txid:
        log.error('Unable to send withdrawal TX')

    AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=tron_manager.get_amount_from_base_denomination(withdrawal_amount),
        tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=txid,
    )

    accumulation_state.state = accumulation_manager.model.STATE_ACCUMULATION_IN_PROCESS
    accumulation_state.save(update_fields=['state', 'updated'])

    # AccumulationDetails.objects.create(
    #     currency=TRX_CURRENCY,
    #     txid=txid,
    #     from_address=address,
    #     to_address=TRX_SAFE_ADDR
    # )

    reciept = res.wait()
    log.info(reciept)
    log.info('Accumulation TX %s sent from %s to %s', txid, wallet.address, TRX_SAFE_ADDR)


@shared_task
def accumulate_trc20(accumulation_state_id):
    accumulation_state = accumulation_manager.get_by_id(accumulation_state_id)
    address = accumulation_state.wallet.address
    currency = accumulation_state.wallet.currency

    token = tron_manager.get_token_by_symbol(currency)
    token_amount_sun = token.get_base_denomination_balance(address)
    token_amount = token.get_amount_from_base_denomination(token_amount_sun)

    if token_amount <= to_decimal(0):
        log.warning('Cant accumulate %s from: %s; Balance too low: %s;',
                    currency, address, token_amount)
        return

    log.info(f'Accumulation {currency} from: {address}; Balance: {token_amount};')

    gas_keeper = tron_manager.get_gas_keeper_wallet()

    # send trx from gas keeper to send tokens
    log.info('Trying to send token fee from GasKeeper')
    res = tron_manager.send_tx(gas_keeper.private_key, address, TRC20_FEE_LIMIT)
    gas_txid = res.get('txid')

    if not res.get('result') or not gas_txid:
        log.error('Unable to send fee TX')

    acc_transaction = AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=tron_manager.get_amount_from_base_denomination(TRC20_FEE_LIMIT),
        tx_type=AccumulationTransaction.TX_TYPE_GAS_DEPOSIT,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=gas_txid,
    )
    accumulation_state.state = accumulation_manager.model.STATE_WAITING_FOR_GAS
    accumulation_state.save(update_fields=['state', 'updated'])

    receipt = res.wait()
    log.info(receipt)

    acc_transaction.complete(is_gas=True)

    wallet = tron_manager.get_user_wallet(currency, address)
    res = token.send_token(wallet.private_key, TRX_SAFE_ADDR, token_amount_sun)
    txid = res.get('txid')

    if not res.get('result') or not txid:
        log.error('Unable to send withdrawal token TX')

    AccumulationTransaction.objects.create(
        accumulation_state=accumulation_state,
        amount=token.get_amount_from_base_denomination(token_amount_sun),
        tx_type=AccumulationTransaction.TX_TYPE_ACCUMULATION,
        tx_state=AccumulationTransaction.STATE_PENDING,
        tx_hash=txid,
    )
    accumulation_state.state = accumulation_manager.model.STATE_ACCUMULATION_IN_PROCESS
    accumulation_state.save(update_fields=['state', 'updated'])

    receipt = res.wait()
    log.info(receipt)
    log.info('Token accumulation TX %s sent from %s to: %s', txid, wallet.address, TRX_SAFE_ADDR)


@shared_task
def accumulate_trx_dust():
    tron_manager.accumulate_dust()
