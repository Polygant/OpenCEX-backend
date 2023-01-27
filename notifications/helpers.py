import json

from django.utils import timezone

from .cache import redis_client
from .commons import ORDER_NOTIFICATIONS_KEY_PREFIX, ORDER_NOTIFICATIONS_EXPIRATION
from .enums import NotificationType


def serialize_order_for_notification(order):
    from core.serializers.orders import NotifyOrderSerializer
    return NotifyOrderSerializer(order).data


def add_notification(order, notification_type):
    key = f'{ORDER_NOTIFICATIONS_KEY_PREFIX}{order.user_id}-{order.id}'
    data = serialize_order_for_notification(order)
    data['type'] = notification_type
    data['date'] = timezone.now()

    redis_client.set(key, json.dumps(data, default=str), ex=ORDER_NOTIFICATIONS_EXPIRATION)


def create_close_order_notification(order):
    add_notification(order, NotificationType.ORDER_CLOSE.value)


def create_open_order_notification(order):
    add_notification(order, NotificationType.ORDER_OPEN.value)


def create_cancel_order_notification(order):
    add_notification(order, NotificationType.ORDER_CANCEL.value)


def get_order_notifications(user_id, destroy=False):
    notifications = []
    keys = redis_client.keys(f'{ORDER_NOTIFICATIONS_KEY_PREFIX}{user_id}-*')

    if keys:
        values = redis_client.mget(keys)

        for value in values:
            order_data = json.loads(value)
            notification_type = order_data.pop('type')
            notification_date = order_data.pop('date')
            notifications.append({
                'data': order_data,
                'date': notification_date,
                'type': notification_type,
            })

        if destroy:
            redis_client.delete(*keys)

    return notifications
