import logging

from celery import group

from core.models.inouts.wallet import WalletTransactions
from core.utils.withdrawal import get_withdrawal_requests_to_process
from cryptocoins.accumulation_manager import AccumulationManager
from cryptocoins.models.accumulation_transaction import AccumulationTransaction
from cryptocoins.tasks.evm import (
    withdraw_coin_task,
    withdraw_tokens_task,
    check_deposit_scoring_task,
    check_balance_task,
    accumulate_tokens_task,
)
from cryptocoins.utils.commons import (
    load_last_processed_block_id,
    store_last_processed_block_id,
)
from lib.utils import memcache_lock

log = logging.getLogger(__name__)
accumulation_manager = AccumulationManager()


class BaseEVMCoinHandler:
    CURRENCY = None
    COIN_MANAGER = None
    TRANSACTION_CLASS = None
    DEFAULT_BLOCK_ID_DELTA = 1000
    SAFE_ADDR = None
    TOKEN_CURRENCIES = None
    TOKEN_CONTRACT_ADDRESSES = None
    BLOCK_GENERATION_TIME = 15
    ACCUMULATION_PERIOD = 60
    COLLECT_DUST_PERIOD = 24 * 60 * 60
    IS_ENABLED = True

    @classmethod
    def process_block(cls, block_id):
        """Check block for deposit, accumulation, withdrawal transactions and schedules jobs"""
        raise NotImplementedError

    @classmethod
    def check_tx_withdrawal(cls, withdrawal_id, tx_data):
        """TX success check """
        raise NotImplementedError

    @classmethod
    def check_balance(cls, wallet_transaction_id):
        """Splits blockchain currency accumulation and token accumulation"""
        raise NotImplementedError

    @classmethod
    def accumulate_coin(cls, wallet_transaction_id):
        raise NotImplementedError

    @classmethod
    def accumulate_tokens(cls, wallet_transaction_id):
        raise NotImplementedError

    @classmethod
    def withdraw_coin(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        raise NotImplementedError

    @classmethod
    def withdraw_tokens(cls, withdrawal_request_id, password, old_tx_data=None, prev_tx_hash=None):
        raise NotImplementedError

    @classmethod
    def process_new_blocks(cls):
        lock_id = f'{cls.CURRENCY.code}_blocks'
        with memcache_lock(lock_id, lock_id) as acquired:
            if acquired:
                current_block_id = cls.COIN_MANAGER.get_latest_block_num()
                default_block_id = current_block_id - cls.DEFAULT_BLOCK_ID_DELTA
                last_processed_block_id = load_last_processed_block_id(
                    currency=cls.CURRENCY, default=default_block_id)

                if last_processed_block_id >= current_block_id:
                    log.debug('Nothing to process since block #%s', current_block_id)
                    return

                blocks_to_process = list(range(
                    last_processed_block_id + 1,
                    current_block_id + 1,
                ))
                blocks_to_process.insert(0, last_processed_block_id)
                blocks_to_process = blocks_to_process[:cls.DEFAULT_BLOCK_ID_DELTA]

                if len(blocks_to_process) > 1:
                    log.info('Need to process blocks #%s..#%s', last_processed_block_id + 1, current_block_id)
                else:
                    log.info('Need to process block #%s', last_processed_block_id + 1)

                for block_id in blocks_to_process:
                    cls.process_block(block_id)

                store_last_processed_block_id(currency=cls.CURRENCY, block_id=current_block_id)

    @classmethod
    def process_coin_deposit(cls, tx_data: dict):
        """
        Process coin deposit, excepting inner gas deposits, etc
        """
        log.info('Processing %s deposit: %s', cls.CURRENCY.code, tx_data)
        tx = cls.TRANSACTION_CLASS(tx_data)
        amount = cls.COIN_MANAGER.get_amount_from_base_denomination(tx.value)

        # skip if failed
        if not cls.COIN_MANAGER.is_valid_transaction(tx.hash):
            log.error(f'{cls.CURRENCY} deposit transaction {tx.hash} is invalid or failed')
            return

        coin_keeper = cls.COIN_MANAGER.get_keeper_wallet()
        external_accumulation_addresses = accumulation_manager.get_external_accumulation_addresses([cls.CURRENCY])

        # is accumulation tx?
        if tx.to_addr in [cls.SAFE_ADDR, coin_keeper.address] + external_accumulation_addresses:
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

            log.info(f'Tx {tx.hash} is {cls.CURRENCY.code} accumulation')
            return

        coin_gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()
        # is inner gas deposit?
        if tx.from_addr == coin_gas_keeper.address:
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
            accumulate_tokens_task.apply_async(
                [cls.CURRENCY.code, accumulation_transaction.wallet_transaction_id],
                queue=f'{cls.CURRENCY.code.lower()}_tokens_accumulations'
            )
            return

        db_wallet = cls.COIN_MANAGER.get_wallet_db_instance(cls.CURRENCY, tx.to_addr)
        if db_wallet is None:
            log.error(f'Wallet {cls.CURRENCY.code} {tx.to_addr} not exists or blocked')
            return

        # is already processed?
        db_wallet_transaction = WalletTransactions.objects.filter(
            tx_hash__iexact=tx.hash,
            wallet_id=db_wallet.id,
        ).first()

        if db_wallet_transaction is not None:
            log.warning(f'TX {tx.hash} already processed as {cls.CURRENCY.code} deposit')
            return

        # make deposit
        # check for keeper deposit
        if db_wallet.address == coin_keeper.address:
            log.info(f'TX {tx.hash} is keeper {cls.CURRENCY.code} deposit: {amount}')
            return

        # check for gas keeper deposit
        if db_wallet.address == coin_gas_keeper.address:
            log.info(f'TX {tx.hash} is gas keeper {cls.CURRENCY.code} deposit: {amount}')
            return

        WalletTransactions.objects.create(
            wallet=db_wallet,
            tx_hash=tx.hash,
            amount=amount,
            currency=cls.CURRENCY,
        )
        log.info(f'TX {tx.hash} processed as {amount} {cls.CURRENCY.code} deposit')

    @classmethod
    def process_tokens_deposit(cls, tx_data: dict):
        """
        Process ERC20 deposit
        """
        log.info(f'Processing {cls.CURRENCY.code} TOKENS deposit: {tx_data}')
        tx = cls.TRANSACTION_CLASS(tx_data)

        if not cls.COIN_MANAGER.is_valid_transaction(tx.hash):
            log.warning(f'{cls.CURRENCY.code} TOKENS deposit TX {tx.hash} is failed or invalid')
            return

        token = cls.COIN_MANAGER.get_token_by_address(tx.contract_address)
        token_to_addr = tx.to_addr
        token_amount = token.get_amount_from_base_denomination(tx.value)
        coin_keeper = cls.COIN_MANAGER.get_keeper_wallet()
        external_accumulation_addresses = accumulation_manager.get_external_accumulation_addresses(
            list(cls.TOKEN_CURRENCIES))

        if token_to_addr in [cls.SAFE_ADDR, coin_keeper.address] + external_accumulation_addresses:
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

        db_wallet = cls.COIN_MANAGER.get_wallet_db_instance(token.currency, token_to_addr)
        if db_wallet is None:
            log.error(f'Wallet {token.currency} {token_to_addr} not exists or blocked')
            return

        db_wallet_transaction = WalletTransactions.objects.filter(
            tx_hash__iexact=tx.hash,
            wallet_id=db_wallet.id,
        ).first()
        if db_wallet_transaction is not None:
            log.warning(f'TX {tx.hash} already processed as {token.currency} deposit')
            return

        # check for keeper deposit
        if db_wallet.address == coin_keeper.address:
            log.info(f'TX {tx.hash} is keeper {token.currency} deposit: {token_amount}')
            return

        # check for gas keeper deposit
        coin_gas_keeper = cls.COIN_MANAGER.get_gas_keeper_wallet()
        if db_wallet.address == coin_gas_keeper.address:
            log.info(f'TX {tx.hash} is keeper {token.currency} deposit: {token_amount}')
            return

        WalletTransactions.objects.create(
            wallet_id=db_wallet.id,
            tx_hash=tx.hash,
            amount=token_amount,
            currency=token.currency,
        )
        log.info(f'TX {tx.hash} processed as {token_amount} {token.currency} deposit')

    @classmethod
    def process_payouts(cls, password, withdrawals_ids=None):
        coin_withdrawal_requests = get_withdrawal_requests_to_process(currencies=[cls.CURRENCY])

        if coin_withdrawal_requests:
            log.info(f'Need to process {len(coin_withdrawal_requests)} {cls.CURRENCY} withdrawals')

            for item in coin_withdrawal_requests:
                if withdrawals_ids and item.id not in withdrawals_ids:
                    continue

                # skip freezed withdrawals
                if item.user.profile.is_payouts_freezed():
                    continue
                withdraw_coin_task.apply_async(
                    [cls.CURRENCY.code, item.id, password],
                    queue=f'{cls.CURRENCY.code.lower()}_payouts'
                )

        tokens_withdrawal_requests = get_withdrawal_requests_to_process(
            currencies=cls.TOKEN_CURRENCIES,
            blockchain_currency=cls.CURRENCY.code,
        )

        if tokens_withdrawal_requests:
            log.info(f'Need to process {len(tokens_withdrawal_requests)} {cls.CURRENCY} TOKENS withdrawals')
            for item in tokens_withdrawal_requests:
                if withdrawals_ids and item.id not in withdrawals_ids:
                    continue
                # skip freezed withdrawals
                if item.user.profile.is_payouts_freezed():
                    continue
                withdraw_tokens_task.apply_async(
                    [cls.CURRENCY.code, item.id, password],
                    queue=f'{cls.CURRENCY.code.lower()}_payouts'
                )

    @classmethod
    def check_deposit_scoring(cls, wallet_transaction_id):
        """Check deposit for scoring"""
        wallet_transaction = accumulation_manager.get_wallet_transaction_by_id(wallet_transaction_id)
        wallet_transaction.check_scoring()

    @classmethod
    def check_balances(cls):
        """Main accumulations scheduler"""
        kyt_check_jobs = []
        accumulations_jobs = []
        external_accumulations_jobs = []

        for item in accumulation_manager.get_waiting_for_kyt_check(cls.CURRENCY):
            kyt_check_jobs.append(check_deposit_scoring_task.s(cls.CURRENCY.code, item.id))

        for item in accumulation_manager.get_waiting_for_accumulation(blockchain_currency=cls.CURRENCY):
            accumulations_jobs.append(check_balance_task.s(cls.CURRENCY.code, item.id))

        for item in accumulation_manager.get_waiting_for_external_accumulation(blockchain_currency=cls.CURRENCY):
            external_accumulations_jobs.append(check_balance_task.s(cls.CURRENCY.code, item.id))

        if kyt_check_jobs:
            log.info('Need to check for KYT: %s', len(kyt_check_jobs))
            jobs_group = group(kyt_check_jobs)
            jobs_group.apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        if accumulations_jobs:
            log.info('Need to check accumulations: %s', len(accumulations_jobs))
            jobs_group = group(accumulations_jobs)
            jobs_group.apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

        if external_accumulations_jobs:
            log.info('Need to check external accumulations: %s', len(external_accumulations_jobs))
            jobs_group = group(external_accumulations_jobs)
            jobs_group.apply_async(queue=f'{cls.CURRENCY.code.lower()}_check_balances')

    @classmethod
    def accumulate_dust(cls):
        cls.COIN_MANAGER.accumulate_dust()
