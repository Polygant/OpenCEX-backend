from django.db.models.signals import post_save
from django.dispatch import receiver

from exchange.notifications import wallet_history_notificator
from exchange.notifications import wallet_topups_history_notificator
from exchange.notifications import wallet_withdrawals_history_notificator
from exchange.notifications import wallet_history_ticker_notificator
from core.models.wallet_history import WalletHistoryItem


@receiver(post_save, sender=WalletHistoryItem)
def notify_new_entry(sender, instance, created, **kwargs):
    wallet_history_notificator.add_data(entry=instance)
    wallet_topups_history_notificator.add_data(entry=instance)
    wallet_withdrawals_history_notificator.add_data(entry=instance)
    wallet_history_ticker_notificator.add_data(entry=instance)
