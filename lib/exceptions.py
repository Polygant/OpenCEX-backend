from typing import Any

from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, status

from lib.utils import camel_to_snake_string


class BaseError(exceptions.APIException):
    """
    Base system error. Should not be raised directly.
    You must set code attribute when inherited.
    """
    status_code = status.HTTP_400_BAD_REQUEST

    def __new__(cls, *args, **kwargs) -> Any:
        """
        Should not be used directly, only inherited
        """
        if cls is BaseError:
            raise RuntimeError('BaseError should not be instantiated directly.')

        cls.code = camel_to_snake_string(cls.__name__)

        # preserve arguments for reraise deserialized exception from tasks
        instance = super().__new__(cls, *args, **kwargs)
        instance._args = args
        instance._kwargs = kwargs

        return instance

    def __init__(self, detail=None, code=None):

        super().__init__(
            detail={
                'message': detail or self.default_detail,
                'type':  code or self.default_code or self.code
            },
            code=self.code
        )


class UnknownError(BaseError):
    default_detail = _('Unknown error.')
