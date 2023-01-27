from modeltranslation.translator import translator, TranslationOptions

from notifications.models.NotificationModels import Mailing
from notifications.models.NotificationModels import Notification


class MailingTranslationOptions(TranslationOptions):
    fields = (
        'subject',
        'text',
    )


class NotificationTranslationOptions(TranslationOptions):
    fields = (
        'title',
        'text',
    )


translator.register(Mailing, MailingTranslationOptions)
translator.register(Notification, NotificationTranslationOptions)
