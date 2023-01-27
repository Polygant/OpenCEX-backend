from typing import List

from django.contrib import messages, admin

from lib.admin import BaseModelAdmin
from notifications.models.NotificationModels import Notification, Mailing


@admin.register(Notification)
class NotificationAdmin(BaseModelAdmin):
    no_delete = False
    fields = ['type', 'title', 'text']
    list_display = ['created', 'title', 'type', 'users_count']

    def users_count(self, obj):
        return obj.users.count()


@admin.register(Mailing)
class MailingAdmin(BaseModelAdmin):
    no_delete = False
    readonly_fields = ['created', 'last_processed']
    fields = ['created', 'subject', 'text', 'users', 'last_processed']
    list_display = ['subject', 'last_processed', 'created', ]
    actions = (
        'proceed',
    )

    def last_processed(self, obj: Mailing):

        processed = obj.processed.latest('pk')
        if processed is not None:
            return processed.created

        return '-'

    @admin.action()
    def proceed(self, request, queryset: List[Mailing]):
        try:
            for item in queryset:
                item.send()
        except Exception as e:
            messages.error(request, e)