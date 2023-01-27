import enum

from django.utils.translation import ugettext_lazy as _


class BaseEnum(enum.Enum):

    @classmethod
    def choices(cls):
        return tuple((i.value, _(i.name)) for i in cls)