import datetime
import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.template import loader
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from core.consts.currencies import CURRENCIES_LIST
from core.models.inouts.dif_balance import DifBalance
from core.models.inouts.dif_balance import DifBalanceMonth
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.sci import PayGateTopup
from core.models.inouts.transaction import TRANSACTION_PENDING
from core.models.inouts.withdrawal import CREATED
from core.models.inouts.withdrawal import WithdrawalRequest
from core.serializers.orders import ExchangeRequestSerializer
from core.withdrawal_processor import SCIPayoutsProcessor
from lib.helpers import to_decimal, pretty_decimal
from lib.orders_helper import get_cost_and_price
from lib.utils import memcache_lock

log = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def cancel_expired_withdrawals():
    """Cancel not confirmed withdrawals after settings.WITHDRAWAL_REQUEST_EXPIRATION_M minutes"""
    expiration_date = timezone.now() - timezone.timedelta(minutes=settings.WITHDRAWAL_REQUEST_EXPIRATION_M)
    log.info('Cancelling withdrawals older than %s', expiration_date)

    qs = WithdrawalRequest.objects.filter(
        state=CREATED,
        created__lt=expiration_date,
        confirmed=False,
    ).only('id')

    for withdrawal_request in qs.iterator():
        withdrawal_request.cancel()


@shared_task
def sync_currencies_with_db():
    """Automatically creates new DisabledCoin entries when new coin has been added and service restarted"""
    for _, symbol in CURRENCIES_LIST:
        DisabledCoin.objects.get_or_create(currency=symbol)


@shared_task
def send_sepa_details_email(id, lang='en'):
    """Sends sepa details to user"""
    pgtu: PayGateTopup = PayGateTopup.objects.filter(id=id).first()
    if not pgtu:
        return
    #TODO check fee if needs
    data = {
        'base_currency': pgtu.currency.code,
        'operation': 1,
        'quantity': pgtu.amount,
        'quote_currency': 'BTC',
    }
    cost, price = get_cost_and_price(pgtu.user, data, ExchangeRequestSerializer)
    c = {
        'quantity': pretty_decimal(pgtu.amount, digits=2),
        'amount': to_decimal(cost),
        'remittance_id': pgtu.data.get('remittance_id')
    }
    msg = loader.get_template(f'sepa_details_text.{lang}.txt').render(c).strip()
    subj = loader.get_template(f'sepa_details_subj.{lang}.txt').render(c).strip()
    send_mail(subj, msg, settings.DEFAULT_FROM_EMAIL, [pgtu.user.email])
    log.info(f'Sepa details has been sent to {pgtu.user.email}')


@shared_task
def withdrawal_failed_email(wd_id):
    """Sends withdrawal failed email to user"""
    wd: WithdrawalRequest = WithdrawalRequest.objects.filter(id=wd_id).first()
    if not wd:
        return

    c = {'username': wd.user.username}
    lang = 'ru' if wd.user.profile.language == 'ru' else 'en'

    msg = loader.get_template(f'withdrawal_failed_text.{lang}.txt').render(c).strip()
    subj = loader.get_template(f'withdrawal_failed_subj.{lang}.txt').render(c).strip()
    send_mail(subj, msg, settings.DEFAULT_FROM_EMAIL, [wd.user.email])
    log.info(f'Withdrawal failed notification has been sent to {wd.user.email}')


@shared_task
def process_withdrawal_requests():
    """Process fiat withdrawals"""
    lock_id = 'sci_process_withdrawal'
    with memcache_lock(lock_id, lock_id, expire=10 * 60) as acquired:
        if acquired:
            SCIPayoutsProcessor().start()


@shared_task
def calculate_dif_balances(period='1d'):
    lock_id = 'dif_balance'
    with memcache_lock(lock_id, lock_id, expire=10 * 60) as acquired:
        if acquired:
            if period == '1d':
                DifBalance.process()
            elif period == '1m':
                DifBalanceMonth.process()


@shared_task
def clean_old_difbalances():
    now = timezone.now()
    diffs = DifBalance.objects.filter(
        created__lt=now - datetime.timedelta(days=7),
        diff=0
    )
    count = diffs.count()
    diffs.delete()
    log.info(f'{count} difbalance entries with 0 difference will be cleaned')


@shared_task
def send_withdrawal_confirmation_email(withdrawal_request_id):
    withdrawal_request = WithdrawalRequest.objects.filter(id=withdrawal_request_id).first()
    if not withdrawal_request:
        return 

    assert withdrawal_request.state == CREATED
    assert withdrawal_request.transaction.state == TRANSACTION_PENDING
    site = Site.objects.get_current()
    token = withdrawal_request.confirmation_token
    confirmation_url = f'https://{site.domain}/account/confirm-withdrawal-request/{token}'
    context = {
        'confirmation_url': confirmation_url,
        'code': token,
    }
    message = loader.get_template('withdrawal_request_confirmation.txt').render(context)

    send_mail(
        subject=_('Withdrawal request confirmation'),
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[withdrawal_request.user.email],
    )
