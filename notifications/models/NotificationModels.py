from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class Notification(models.Model):
    TYPE_SPLASH = 1
    TYPE_SUCCESS_MESSAGE = 2
    TYPE_FAILED_MESSAGE = 3

    TYPES = (
        (TYPE_SPLASH, 'Splash'),
        (TYPE_SUCCESS_MESSAGE, 'Success message'),
        (TYPE_FAILED_MESSAGE, 'Fail message'),
    )

    created = models.DateTimeField(default=timezone.now)
    title = models.CharField(max_length=255, default='')
    text = models.TextField(default='')
    type = models.PositiveSmallIntegerField(choices=TYPES, default=TYPE_SPLASH)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='notifications')

    def save(self, *args, **kwargs):
        super(Notification, self).save(*args, **kwargs)

    def add_all_users(self):
        self.users.clear()
        self.users.set(User.objects.all())


class Mailing(models.Model):
    created = models.DateTimeField(default=timezone.now)
    subject = models.CharField(max_length=250, default=None, blank=True)
    text = models.TextField(default=None, blank=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='mailing')

    def send(self):
        from notifications.tasks import send_email_message

        for user in self.users.all():
            lang = user.profile.language
            params = {
                'subject': getattr(self, 'subject_'+lang),
                'text': getattr(self, 'text_'+lang),
                'email': user.email,
                'lang': lang,
                'user_id': user.id,
            }
            send_email_message.apply_async([params], queue='mailing')

        processed = MailingProcessed(mailing=self)
        processed.save()


class MailingProcessed(models.Model):
    created = models.DateTimeField(default=timezone.now)
    mailing = models.ForeignKey(Mailing, on_delete=models.deletion.CASCADE, related_name='processed')
