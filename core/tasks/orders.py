import datetime
import logging

import requests
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.contrib.sites.models import Site
from django.core import serializers
from django.core.mail import send_mail
from django.db.models.aggregates import Sum
from django.db.transaction import atomic
from django.template import loader
from django.utils import timezone

from core.cache import PAIRS_VOLUME_CACHE_KEY
from core.cache import orders_app_cache
from core.consts.currencies import ALL_CURRENCIES
from core.consts.orders import STOP_LIMIT
from core.currency import Currency
from core.orderbook.helpers import get_stack_by_pair
from core.models import PairSettings
from core.models.facade import Profile
from core.models.inouts.transaction import REASON_FEE_TOPUP, REASON_ORDER_EXTRA_CHARGE, REASON_ORDER_CHARGE_RETURN
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.transaction import Transaction
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.models.orders import OrderChangeHistory
from core.models.inouts.pair import Pair
from core.serializers.orders import OrderSerializer, ExecutionResultApiSerializer
from core.stack_processor import StackProcessor
from core.utils.cleanup_utils import get_orders_to_delete_ids, strip_orders
from core.utils.cleanup_utils import get_transactions_to_delete_ids, strip_transactions
from core.utils.stats.daily import get_pairs_24h_stats
from exchange.notifications import pairs_volume_notificator
from lib.backup_utils import finish_backup
from lib.backup_utils import prepare_backup
from lib.helpers import make_hmac_signature_headers
from lib.tasks import WrappedTaskManager

log = logging.getLogger(__name__)
User = get_user_model()


@shared_task()
def place_order(data):
    #  TODO вынести StackProcessor
    stack_processor: StackProcessor = StackProcessor.get_instance()
    stack_processor.place_order(data)


@shared_task
def update_order_wrapped(data):
    """Updates order via stack worker for the specified pair"""
    try:
        stack_processor = StackProcessor.get_instance()
        stack_processor.update_order(data)

        return WrappedTaskManager.pack_result()

    except Exception as exc:
        return WrappedTaskManager.pack_exception(exc)


@shared_task
def cancel_order(data):
    """Cancel order via stack worker for the specified pair"""
    order_id = data['order_id']
    data['id'] = order_id
    stack_processor: StackProcessor = StackProcessor.get_instance()
    stack_processor.cancel_order(data)


@shared_task
def market_order(data):
    """Creates market order via stack worker for the specified pair"""
    data['pair'] = Pair.get(data['pair_id'])
    stack_processor: StackProcessor = StackProcessor.get_instance()
    return stack_processor.market_order(data)


@shared_task
def market_order_wrapped(data):
    """Creates market order via stack worker for the specified pair"""
    return WrappedTaskManager.wrap_fn(market_order, data)


@shared_task
def exchange_order(data):
    """Creates exchange order via stack worker for the specified pair"""
    stack_processor = StackProcessor.get_instance()
    data['base_currency'] = Currency.get(data['base_currency'])
    data['quote_currency'] = Currency.get(data['quote_currency'])
    data['pair'] = Pair.get(data['pair_id'])
    return stack_processor.exchange_order(data)


@shared_task
def exchange_order_wrapped(data):
    """Creates exchange order via stack worker for the specified pair"""
    return WrappedTaskManager.wrap_fn(exchange_order, data)


@shared_task
def stop_limit_order(data):
    """Creates stop limit order via stack worker for the specified pair"""
    data['pair'] = Pair.get(data['pair_id'])
    stack_processor: StackProcessor = StackProcessor.get_instance()
    return stack_processor.stop_limit_order(data)


@shared_task
def stop_limit_order_wrapped(data):
    """Creates stop limit order via stack worker for the specified pair"""
    return WrappedTaskManager.wrap_fn(stop_limit_order, data)


@shared_task
def stop_limit_processor(data):
    stack_processor: StackProcessor = StackProcessor.get_instance()
    order: Order = stack_processor.get_order_from_json(data)
    log.info(f'stop_limit_processor: %s' % order)

    matched: ExecutionResult = order.executionresult_set.last()
    if matched:
        stacks = get_stack_by_pair(matched.pair.code)
        if order.operation == order.OPERATION_SELL:
            stack = stacks.get('buys', [])
            ids = [i['id'] for i in stack]

            orders = Order.objects.exclude(
                pk__in=ids
            ).filter(
                state=order.STATE_OPENED,
                quantity_left__gt=0,
                type=STOP_LIMIT,
                stop__lte=matched.price,
                pair=matched.pair,
                operation=order.OPERATION_BUY,
            ).all()
        else:
            stack = stacks.get('sells', [])
            ids = [i['id'] for i in stack]

            orders = Order.objects.exclude(
                pk__in=ids
            ).filter(
                state=order.STATE_OPENED,
                quantity_left__gt=0,
                type=STOP_LIMIT,
                stop__gte=matched.price,
                pair=matched.pair,
                operation=order.OPERATION_SELL
            ).all()

        for order_item in orders:
            order_item: Order
            data_order = serializers.serialize('json', [order_item])
            order_item.in_stack = True

            args = [data_order]
            place_order.apply_async(args, queue=order_item.queue())
            log.info(f'stop_limit_processor->place_order: %s' % order_item)

        Order.objects.bulk_update(orders, ['in_stack'], batch_size=20000)


@shared_task
def otc_orders_price_update():
    """Run price updaters for auto-order enabled pairs"""
    for pair_code in PairSettings.get_autoorders_enabled_pairs():
        run_otc_orders_price_update.apply_async([pair_code], queue=f'orders.{pair_code}')


@shared_task
def run_otc_orders_price_update(pair='BTC-USDT'):
    """Updates price for auto-orders by pair"""
    if pair not in PairSettings.get_autoorders_enabled_pairs():
        return
    stack_processor: StackProcessor = StackProcessor.get_instance()
    stack_processor.otc_bulk_update(pair)


@shared_task
def pairs_24h_stats_cache_update():
    """Periodically updates cache for pairs 24h stats"""
    orders_app_cache.set(PAIRS_VOLUME_CACHE_KEY, get_pairs_24h_stats())
    pairs_volume_notificator.add_data()


@shared_task
def aggregate_fee(use_prev_day=True):
    """Collects daily fees to special user, specified in settings.FEE_USER"""
    log.info('fee aggregate started')
    fee_user = User.objects.filter(email=settings.FEE_USER).first()
    if not fee_user:
        log.error('No fee user found! check settings!')
        return
    for c in ALL_CURRENCIES:
        with atomic():
            qs = ExecutionResult.objects \
                .filter(cancelled=False, fee_aggregate_tx__isnull=True, fee_amount__gt=0) \
                .filter(transaction__currency=c)

            if use_prev_day:
                prev_day = (timezone.now() - datetime.timedelta(days=1)).replace(
                    minute=0, second=0, hour=0, microsecond=0
                )
                qs = qs.filter(created__lt=prev_day)
            fee_amount = qs.aggregate(total=Sum('fee_amount'))['total']
            log.info(f'total fee amount for {c.code} is {fee_amount}')
            if not fee_amount:
                continue

            t = Transaction(reason=REASON_FEE_TOPUP, state=TRANSACTION_COMPLETED, currency=c, amount=fee_amount, user=fee_user)
            t.save()
            qs.update(fee_aggregate_tx=t)


def send_api_callback(user_id, order_id):
    """Sends order info to user """
    from core.utils.facade import get_cached_api_callback_url

    cb = get_cached_api_callback_url(user_id)
    if cb:
        send_order_changed_api_callback_request.apply_async([
            order_id,
            user_id,
        ])


@shared_task
def send_order_changed_api_callback_request(order_id, user_id):
    profile = Profile.objects.filter(user_id=user_id).only('api_callback_url').first()

    if not profile.api_callback_url:
        return

    order = Order.objects.filter(pk=order_id).first()
    data = OrderSerializer(order).data

    er_qs = ExecutionResult.objects.filter(
        order_id=order_id,
        cancelled=False,
    ).only(
        'id',
        'price',
        'quantity',
    )
    data['matches'] = ExecutionResultApiSerializer(er_qs, many=True).data

    headers = make_hmac_signature_headers(order.user.profile.api_key, order.user.profile.secret_key)
    requests.post(
        url=order.user.profile.api_callback_url,
        json=data,
        headers=headers,
    )


@shared_task
def send_exchange_completed_message(params, lang='en'):
    """Sends email to user that exchange completed"""
    site_domain = Site.objects.get_current().domain

    params['site_domain'] = site_domain

    email = params['email']
    msg = loader.get_template(f'email/exchange_completed_message.{lang}.txt').render(params).strip()
    subject = loader.get_template(f'email/exchange_completed_message_subject.{lang}.txt').render(params).strip()
    send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [email])


@shared_task
def send_exchange_expired_message(params, lang='en'):
    """Sends email to user that exchange expired"""
    email = params['email']
    msg = loader.get_template(f'email/exchange_expired_message.{lang}.txt').render(params).strip()
    subject = loader.get_template(f'email/exchange_expired_message_subject.{lang}.txt').render(params).strip()
    send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [email])


@shared_task
def bot_matches_cleanup(only_backup=False):
    """Cleans bot-bot matches and relevant orders and transactions"""
    prepare_backup()
    start_time = timezone.now()
    log.info('+' * 10)
    log.info('Get order ids')
    order_ids = get_orders_to_delete_ids()
    log.info('Start cleanup orders')
    strip_orders(order_ids, only_backup)
    log.info('Done orders: %s', timezone.now() - start_time)

    log.info('+' * 10)
    log.info('Get transaction ids')
    transaction_ids = get_transactions_to_delete_ids()
    log.info('Txs without foreign count: %s', len(transaction_ids))
    log.info('Start cleanup transaction without foreign')
    strip_transactions(transaction_ids, only_backup)
    log.info('Done transactions: %s', timezone.now() - start_time)

    log.info('Done: %s', timezone.now() - start_time)
    log.info('+' * 10)
    finish_backup()


@shared_task
def cleanup_old_order_changes():
    log.info('Cleanup old orders changes history')
    month_ago = timezone.now() - datetime.timedelta(days=30)
    res = OrderChangeHistory.objects.filter(
        created__lt=month_ago,
    ).delete()
    if res:
        log.info(f'{res[0]} user change items deleted')


@shared_task()
def cleanup_extra_transactions():
    """Collapse update order transaction to one transaction"""
    ts_start = timezone.now()
    ago = timezone.now() - datetime.timedelta(days=3)

    #  aggreggates transactions by order_id
    grouped_extra_transactions = Transaction.objects.filter(
        state=TRANSACTION_COMPLETED,
        reason__in=(
            REASON_ORDER_EXTRA_CHARGE,
            REASON_ORDER_CHARGE_RETURN,
        ),
        created__lt=ago,
    ).annotate(
        oid=KeyTextTransform('order_id', 'data')
    ).values('oid').annotate(
        summ=Sum('amount'),
        tx_ids=ArrayAgg('id')
    ).values(
        'oid', 'summ', 'tx_ids'
    ).order_by('oid')

    log.info(f'query time: %s' % (timezone.now() - ts_start))

    for_start = timezone.now()
    count_tr: int = 0
    count_or: int = 0

    for entry in grouped_extra_transactions:
        order_start = timezone.now()
        tr_list = entry['tx_ids']
        order_id = int(entry['oid'])
        if len(tr_list) <= 1:
            continue

        first_tx_id = tr_list[0]
        to_delete_tx_ids = tr_list[1:]
        sum_amount = entry['summ']

        reason = REASON_ORDER_CHARGE_RETURN if sum_amount > 0 else REASON_ORDER_EXTRA_CHARGE
        with atomic():
            # Update only first tx in group
            Transaction.objects.filter(id=first_tx_id).update(reason=reason, amount=sum_amount)
            deleted_count = len(to_delete_tx_ids)

            # delete other group txs
            q = Transaction.objects.filter(pk__in=to_delete_tx_ids)
            q.delete()
            log.info(f'==order id: {order_id}, time: {timezone.now() - order_start}, deleted txs: {deleted_count}')
            count_or += 1
            log.info(f'Checked {count_or}/{len(grouped_extra_transactions)}')

    log.info(f'for time: %s' % (timezone.now() - for_start))

    log.info(f'count orders: %s' % (count_or))
    log.info(f'count transactions: %s' % (count_tr))
    log.info(f'Duration: %s' % (timezone.now() - ts_start))
