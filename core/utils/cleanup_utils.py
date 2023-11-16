import itertools
import logging

from django.db import connection
from django.db.models import Case, When, Q, F, Count, IntegerField
from django.db.transaction import atomic
from django.utils import timezone

from core.consts.orders import ORDER_OPENED, ORDER_CANCELED
from core.models import WalletHistoryItem
from core.models.inouts.transaction import REASON_ORDER_OPENED, REASON_ORDER_EXECUTED, REASON_ORDER_CANCELED
from core.models.inouts.transaction import Transaction
from core.models.orders import ExecutionResult, Order, OrderChangeHistory, OrderStateChangeHistory
from lib.backup_utils import backup_qs_to_csv
from lib.helpers import BOT_RE
from lib.helpers import chunked

log = logging.getLogger(__name__)

DEFAULT_BEFORE_DELTA = timezone.timedelta(days=7)
DEFAULT_BATCH_SIZE = 10_000


# startdate = datetime.datetime(2021,7,8,10,15)

get_ids_sql = """
select
       o.id as order_id,
       array_remove(array_agg(distinct er.id), NULL) as er_ids,
       array_remove(array_agg(distinct tr_ercb.id) || array_agg(distinct tr_o_in.id) || array_agg(distinct tr_er.id), NULL) as tr_ids,
       array_remove(array_agg(distinct whi.id), NULL) as whi_ids
from core_order o
left outer join core_executionresult er on er.order_id = o.id or er.matched_order_id = o.id
left outer join core_transaction tr_o_in on tr_o_in.id = o.in_transaction_id
left outer join core_transaction tr_er on tr_er.id = er.transaction_id
left outer join core_transaction tr_ercb on tr_ercb.id = er.cacheback_transaction_id
left outer join core_wallethistoryitem whi on whi.transaction_id = o.in_transaction_id
where o.id = any(%s)
group by o.id;
"""

def get_bot_matches_qs(ts_before):
    """
    Specific function to process bot-bot matches cleanup
    """
    return ExecutionResult.objects.filter(
        ~Q(Q(order__state=ORDER_OPENED) | Q(created__gte=ts_before)),
        cancelled=False,
        user__username__iregex=BOT_RE,
        order__user__username__iregex=BOT_RE,
        matched_order__user__username__iregex=BOT_RE,
        # created__gt=startdate
    ).only(
        'order_id',
        'matched_order',
    ).order_by('id')


def get_bot_excluded_matches_qs(order_ids):
    return ExecutionResult.objects.filter(
        Q(order_id__in=order_ids) | Q(matched_order_id__in=order_ids),
        ~Q(order__user__username__iregex=BOT_RE) |
        (Q(matched_order__isnull=False) & ~Q(matched_order__user__username__iregex=BOT_RE))
    ).only(
        'order_id',
        'matched_order_id'
    )


def get_bot_matched_without_exr_qs(ts_before):
    """
    Specific function to process bot-bot matches cleanup
    """

    return Order.objects.filter(
        user__username__iregex=BOT_RE,
    ).filter(
        ~Q(state=ORDER_OPENED) &
        Q(executionresult__isnull=True) &
        Q(created__lte=ts_before)
    )


def get_bot_tr_qs(ts_before):
    """
    Specific function to process bot-bot matches cleanup
    """

    return Transaction.objects.filter(
        user__username__iregex=BOT_RE,
        reason__in=(REASON_ORDER_OPENED, REASON_ORDER_EXECUTED, REASON_ORDER_CANCELED),
        order_in_transaction__isnull=True,
        executionresult__cacheback_transaction__isnull=True,
        executionresult__transaction__isnull=True,
        created__lte=ts_before
    )


def list_bots_cancelled():
    """
    Specific function to process bot cancelled cleanup
    """
    qs = Order.objects.filter(
        user__username__iregex=BOT_RE,
    ).filter(
        state=ORDER_CANCELED,
        quantity=F('quantity_left')
    ).annotate(
        non_cancel_results=Count(
            Case(
                When(executionresult__cancelled=False, then=1),
                output_field=IntegerField(),
            )
        ),
    ).filter(
        non_cancel_results=0,
    )
    return qs


def get_transactions_to_delete_ids():
    start_time = timezone.now()
    bot_tr_qs = get_bot_tr_qs(ts_before=timezone.now() - DEFAULT_BEFORE_DELTA)
    bot_transactions_ids = []

    bot_transactions_ids += bot_tr_qs.values_list('id', flat=True)
    log.info('Bot transactions all count: %s', len(bot_transactions_ids))
    return bot_transactions_ids


def get_bot_match_orders_ids(qs):
    """
    Find only bots orders
    """
    res = []
    for match in qs.iterator():
        ids = list(filter(None, [match.order_id, match.matched_order_id]))
        res.extend(ids)
    return set(res)


def get_orders_to_delete_ids():
    start_time = timezone.now()
    all_orders_ids = set()
    # find cancelled bot orders
    cancelled_order_ids = list(list_bots_cancelled().values_list('id', flat=True))
    log.info('Cancelled orders count: %s', len(cancelled_order_ids))

    log.info(timezone.now() - start_time)

    # find all matches bot-bot
    bot_matched_qs = get_bot_matches_qs(ts_before=timezone.now() - DEFAULT_BEFORE_DELTA)
    bot_match_order_ids = get_bot_match_orders_ids(bot_matched_qs)

    log.info('Bot match orders count: %s', len(bot_match_order_ids))

    # find orders with empty match
    bot_matched_without_exr_qs = get_bot_matched_without_exr_qs(ts_before=timezone.now() - DEFAULT_BEFORE_DELTA)
    log.info('Bot match orders without match_model: %s', bot_matched_without_exr_qs.count())
    bot_matched_without_exr_ids = bot_matched_without_exr_qs.values_list('id', flat=True)

    all_orders_ids = all_orders_ids.union(set(cancelled_order_ids))
    all_orders_ids = all_orders_ids.union(set(bot_match_order_ids))
    all_orders_ids = all_orders_ids.union(set(bot_matched_without_exr_ids))

    # exclude user-bot orders and matches
    bot_match_order_excluded_ids = set()
    for chunk in chunked(all_orders_ids, DEFAULT_BATCH_SIZE):
        bot_match_order_excluded_qs = get_bot_excluded_matches_qs(chunk)
        excluded_ids = get_bot_match_orders_ids(bot_match_order_excluded_qs)
        bot_match_order_excluded_ids = bot_match_order_excluded_ids.union(excluded_ids)

    all_orders_ids = list(all_orders_ids - bot_match_order_excluded_ids)

    log.info('Bot match orders all count: %s', len(all_orders_ids))
    log.info(timezone.now() - start_time)

    return all_orders_ids


def strip_transactions(transaction_ids, only_backup=False):
    start_time = timezone.now()
    log.info(f'Total transactions to strip ids count: %s', len(transaction_ids))
    log.info(start_time)
    tx_counter = 1
    all_tr_counter = 0
    al_tr = len(transaction_ids)
    for tx_chunk in chunked(transaction_ids, DEFAULT_BATCH_SIZE):
        with atomic():
            log.info('Batch %s', tx_counter * DEFAULT_BATCH_SIZE)
            log.info(timezone.now() - start_time)

            txs_qs = Transaction.objects.filter(id__in=list(tx_chunk))
            backup_qs_to_csv(txs_qs)

            if not only_backup:

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        delete from core_transaction
                        where id = any(%s)
                        """,
                        [list(tx_chunk)],
                    )

                tx_counter += 1
                all_tr_counter += len(list(tx_chunk))
                log.info('All Transaction count: %s/%s', all_tr_counter, al_tr)
                log.info('=' * 10)


def strip_orders(order_ids, only_backup=False):
    start_time = timezone.now()
    log.info(f'Total orders to strip ids count: %s', len(order_ids))
    log.info(start_time)

    counter = 1
    all_er = 0
    all_tr = 0
    all_or = 0
    all_whi = 0
    for chunk in chunked(order_ids, DEFAULT_BATCH_SIZE):
        with atomic():
            log.info('Batch %s', counter * DEFAULT_BATCH_SIZE)
            log.info(timezone.now() - start_time)
            with connection.cursor() as cursor:
                cursor.execute(get_ids_sql, [list(chunk)])
                results = cursor.fetchall()

                # extract ids
                er_ids = list(map(lambda x: x[1], results))
                tx_ids = list(map(lambda x: x[2], results))
                whi_ids = list(map(lambda x: x[3], results))

                er_ids = list(set(itertools.chain.from_iterable(er_ids)))
                tx_ids = list(set(itertools.chain.from_iterable(tx_ids)))
                whi_ids = list(set(itertools.chain.from_iterable(whi_ids)))

            log.info('ExecutionResult count: %s', len(er_ids))
            log.info('Transaction count: %s', len(tx_ids))
            log.info('WalletHistoryItem count: %s', len(whi_ids))

            txs_qs = Transaction.objects.filter(id__in=tx_ids)
            er_qs = ExecutionResult.objects.filter(id__in=er_ids)
            orders_qs = Order.objects.filter(id__in=list(chunk))
            wallet_history_qs = WalletHistoryItem.objects.filter(id__in=whi_ids)

            backup_qs_to_csv(txs_qs)
            backup_qs_to_csv(er_qs)
            backup_qs_to_csv(orders_qs)
            backup_qs_to_csv(wallet_history_qs)

            if not only_backup:
                log.info('Delete ExecutionResult')
                er_qs._raw_delete(er_qs.db)

                log.info('Delete OrderChangeHistory')
                order_change_history_qs = OrderChangeHistory.objects.filter(id__in=list(chunk))
                order_change_history_qs._raw_delete(order_change_history_qs.db)

                log.info('Delete OrderStateChangeHistory')
                order_state_change_history_qs = OrderStateChangeHistory.objects.filter(id__in=list(chunk))
                order_state_change_history_qs._raw_delete(order_state_change_history_qs.db)

                log.info('Delete Order')
                orders_qs._raw_delete(orders_qs.db)

                log.info('Delete Transaction')
                tx_counter = 0
                for tx_chunk in chunked(tx_ids, DEFAULT_BATCH_SIZE):
                    log.info('Tx chunk %s', tx_counter * DEFAULT_BATCH_SIZE)
                    log.info(timezone.now() - start_time)
                    transaction_qs = Transaction.objects.filter(id__in=list(tx_chunk))
                    transaction_qs._raw_delete(transaction_qs.db)
                    wallet_history_item_qs = WalletHistoryItem.objects.filter(transaction__in=list(tx_chunk))
                    wallet_history_item_qs._raw_delete(wallet_history_item_qs.db)

                    tx_counter += 1

                counter += 1
                all_er += len(er_ids)
                all_tr += len(tx_ids)
                all_or += len(list(chunk))
                all_whi += len(whi_ids)
                log.info('All ExecutionResult count: %s', all_er)
                log.info('All Transaction count: %s', all_tr)
                log.info('All Order count: %s', all_or)
                log.info('All WalletHistoryItem count: %s', all_whi)
                log.info('=' * 10)
