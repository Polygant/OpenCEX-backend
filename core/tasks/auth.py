from allauth.account.models import EmailConfirmation
from celery import shared_task


@shared_task(name="core.tasks.auth.delete_expired_conformation")
def delete_expired_conformation() -> None:
    EmailConfirmation.objects.delete_expired_confirmations()
