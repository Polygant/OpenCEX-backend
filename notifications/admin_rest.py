from typing import List

from django.contrib import messages

from admin_rest import restful_admin as api_admin
from admin_rest.restful_admin import DefaultApiAdmin
from notifications.models.NotificationModels import Notification, Mailing


@api_admin.register(Notification)
class NotificationApiAdmin(DefaultApiAdmin):
    fields = ['type', 'title', 'text']
    list_display = ['created', 'title', 'type', 'users_count']

    def users_count(self, obj):
        return obj.users.count()


@api_admin.register(Mailing)
class MailingApiAdmin(DefaultApiAdmin):
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

    @api_admin.action(permissions=True)
    def proceed(self, request, queryset: List[Mailing]):
        try:
            for item in queryset:
                item.send()
        except Exception as e:
            messages.error(request, e)