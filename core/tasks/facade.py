import datetime
import websocket

from celery.app import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.mail import send_mail
from django.db.models import Q
from django.template import loader
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from core.models.facade import AccessLog
from core.models.facade import LoginHistory
from core.models.facade import UserKYC
from lib.services.sumsub_client import SumSubClient
from lib.notifications import send_telegram_message
from lib.utils import get_domain


@shared_task
def pong():
    """Checks websockets alivement. Send telegram alert if websockets do not respond"""
    try:
        domain = get_domain()
        ws = websocket.create_connection(f"wss://{domain}/wsapi/v1/live_notifications", timeout=10)
        ws.send('{"command":"ping"}')
        result = ws.recv()
        if not result:
            send_telegram_message("Empty response from socket")
        ws.close()
    except Exception as e:
        error = f"Error: {e}"
        send_telegram_message(error)


@shared_task
def plan_kyc_data_updates():
    """Checks latest kyc update and plan new kyc update"""
    last_updated_ts = now() - relativedelta(seconds=settings.KYC_DATA_UPDATE_PERIOD)

    qs = UserKYC.objects.exclude(
        applicantId=''
    ).filter(
        Q(last_kyc_data_update__lt=last_updated_ts) |
        Q(last_kyc_data_update__isnull=True)
    )

    if settings.KYC_DATA_UPDATE_TASKS_AT_ONCE is not None:
        qs = qs[:settings.KYC_DATA_UPDATE_TASKS_AT_ONCE]

    for userkyc in qs:
        update_kyc_data_for_user.apply_async([userkyc.user_id], queue='kyc')


@shared_task
def update_kyc_data_for_user(user_id):
    """Updates KYC data for selected user"""
    userkyc = UserKYC.objects.get(
        user_id=user_id
    )

    if not userkyc.applicantId:
        return

    client = SumSubClient(host='https://test-api.sumsub.com' if settings.DEBUG else SumSubClient.HOST)

    userkyc.kyc_data = client.get_applicant_data(
        userkyc.applicantId
    )
    userkyc.last_kyc_data_update = now()
    userkyc.save()


@shared_task
def clear_sessions():
    """Clear django default sessions"""
    SessionStore.clear_expired()


@shared_task
def clear_old_logs():
    """Clear old AccessLog entries"""
    two_weeks_ago = timezone.now() - datetime.timedelta(days=14)
    AccessLog.objects.filter(created__lt=two_weeks_ago).delete()


@shared_task
def clear_login_history():
    """Clear users login history. Keeps only last 100 entries per each user"""
    pk_to_keep = []
    users_qs = LoginHistory.objects.values_list('user_id', flat=True).distinct()
    for user_id in users_qs:
        ids = LoginHistory.objects.filter(user_id=user_id).order_by('-created').values_list('id', flat=True)[:100]
        pk_to_keep.extend(list(ids))
    LoginHistory.objects.exclude(pk__in=pk_to_keep).delete()


@shared_task
def notify_sof_verification_request_admin(user_id):
    """
    Send email to admin when user saves it state
    """
    user = get_user_model().objects.filter(pk=user_id).first()

    subject = _('SoF verification requested')
    msg_tpl = _('User {username} requested SoF verification.')
    msg = force_text(msg_tpl).format(
        username=user.username,
    )

    send_mail(
        subject=subject,
        message=msg,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
    )


@shared_task
def notify_sof_verification_request_user(user_id):
    """
    Send email to user when user saves it state
    """
    user = get_user_model().objects.filter(pk=user_id).first()

    subject = _('Source of funds verification request')
    msg = _('Your Source of funds request is being processed.')

    send_mail(
        subject=subject,
        message=msg,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task
def notify_sof_request_status_changed_user(user_id):
    """
    Send email to user when sof state changed
    """
    user = get_user_model().objects.filter(pk=user_id).first()

    subject = _('Source of funds status')
    msg = _('Your Source of funds status has been updated.')

    send_mail(
        subject=subject,
        message=msg,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task
def notify_user_ip_changed(user_id, ip):
    """
    Send email to user that there was an attempt to login from a new ip address
    """
    user = get_user_model().objects.filter(pk=user_id).first()
    lang = user.profile.language

    params = {
        'username': user.username,
        'ip_address': ip
    }

    msg = loader.get_template(f'email/ip_changed_message.{lang}.txt').render(params).strip()
    subject = loader.get_template(f'email/ip_changed_subject.{lang}.txt').render({}).strip()
    send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [user.email])


@shared_task
def notify_failed_login(user_id):
    """
    Send email to user that there was an attempt to login with incorrect password
    """
    user = get_user_model().objects.filter(pk=user_id).first()
    lang = user.profile.language

    params = {
        'username': user.username,
    }

    msg = loader.get_template(f'email/failed_login_message.{lang}.txt').render(params).strip()
    subject = loader.get_template(f'email/failed_login_subject.{lang}.txt').render({}).strip()
    send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [user.email])
