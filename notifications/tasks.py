from django.conf import settings
from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.template.loader import render_to_string


@shared_task
def send_email_message(params):
    current_site = Site.objects.get_current()
    params['current_site'] = current_site
    email = params['email']
    user = get_user_model().objects.filter(pk=params['user_id']).first()
    if user is not None:
        params['user'] = user
    subject = render_to_string(f'mailing/email/subject.txt', params).strip()
    msg = render_to_string(f'mailing/email/message.txt', params).strip()
    send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [email])
