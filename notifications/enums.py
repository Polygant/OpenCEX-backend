from enum import Enum


class NotificationType(Enum):
    ORDER_OPEN = 'ORDER_OPEN'
    ORDER_CANCEL = 'ORDER_CANCEL'
    ORDER_CLOSE = 'ORDER_CLOSE'

    @classmethod
    def list(self):
        return [(item.name, item.value) for item in NotificationType]
