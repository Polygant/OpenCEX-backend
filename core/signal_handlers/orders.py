from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

from core.models.facade import Profile
from core.models.orders import ExecutionResult
from core.utils.facade import set_cached_api_callback_url
from exchange.notifications import trades_notificator


@receiver(post_save, sender=Profile)
def update_cached_api_callback_url(sender, instance, created, **kwargs):
    set_cached_api_callback_url(instance.user_id, instance.api_callback_url)


@receiver(post_save, sender=ExecutionResult)
def order_matched(instance, **kwargs):
    er: ExecutionResult = instance
    if er.order_id and er.matched_order_id and (er.order_id - er.matched_order_id > 0) and not er.cancelled:
        trades_notificator.add_data(entry=er)


# @receiver(post_save, sender=Order)
# def order_saved(instance, **kwargs):
#     order: Order = instance
#     if order.state == Order.STATE_OPENED:
#         opened_orders_notificator.add_data(entry=order)
#         opened_orders_by_pair_notificator.add_data(entry=order)
#     else:
#         opened_orders_notificator.add_data(entry=order, delete=True)
#         opened_orders_by_pair_notificator.add_data(entry=order, delete=True)
#         closed_orders_notificator.add_data(entry=order)
#         closed_orders_by_pair_notificator.add_data(entry=order)
