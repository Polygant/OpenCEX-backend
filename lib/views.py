"""
Views-related utils collection
"""

import logging

from lib.utils import exception_handler

log = logging.getLogger(__name__)


class ExceptionHandlerMixin:
    """
    Set exception handler for view until global handling would be enabled
    """

    # noinspection PyMethodMayBeStatic
    def get_exception_handler(self):
        return exception_handler
