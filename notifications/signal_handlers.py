from django.dispatch import receiver

from core.models.orders import Order
from core.signals.orders import market_order_closed
from notifications.helpers import create_close_order_notification


@receiver(market_order_closed, sender=Order)
def on_market_order_closed(sender, order: Order, **kwargs):
    create_close_order_notification(order)
