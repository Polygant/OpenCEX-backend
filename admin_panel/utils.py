from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.utils.functional import cached_property

from lib.helpers import BOT_RE


class MyPaginator(Paginator):
    @cached_property
    def count(self):
        num = self.object_list.values('id').count()
        return num

def get_bots_ids():
    return list(User.objects.filter(username__iregex=BOT_RE).values_list('id', flat=True))
