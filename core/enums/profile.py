from django.utils.translation import ugettext_lazy as _

from core.enums.base import BaseEnum


class UserTypeEnum(BaseEnum):
    user = 1
    staff = 2
    bot = 3
