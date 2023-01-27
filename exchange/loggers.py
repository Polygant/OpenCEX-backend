import logging
from logging import LogRecord

transaction_logger = logging.getLogger('transaction')
transaction_logger.setLevel(logging.DEBUG)


class StaticFieldFilter(logging.Filter):
    """
    Python logging filter that adds the given static contextual information
    in the ``fields`` dictionary to all logging records.
    """

    static_fields = {}

    def __init__(self, name='', fields=None):

        super().__init__(name)
        if fields is not None:
            self.static_fields = fields

    def filter(self, record: LogRecord):
        for k, v in self.static_fields.items():
            setattr(record, k, v)
        return True


class DynamicFieldFilter(StaticFieldFilter):

    @staticmethod
    def set_fields(data):
        DynamicFieldFilter.static_fields = data
        return DynamicFieldFilter

    @staticmethod
    def clear_fields():
        DynamicFieldFilter.static_fields = {}
        return DynamicFieldFilter

    @staticmethod
    def add_field(name, value, clear=True):
        if clear:
            DynamicFieldFilter.clear_fields()
        DynamicFieldFilter.static_fields[name] = value
        return DynamicFieldFilter

    def filter(self, record: LogRecord):
        result = super().filter(record)
        DynamicFieldFilter.clear_fields()
        return result
