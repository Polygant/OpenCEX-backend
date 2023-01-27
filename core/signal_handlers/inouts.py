from django.db.models.signals import post_save
from django.dispatch import receiver

from core.balance_manager import BalanceManager
from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
from core.models.inouts.sci import PayGateTopup
from core.models.inouts.transaction import Transaction
from core.models.inouts.wallet import WalletTransactions
from core.models.inouts.withdrawal import WithdrawalRequest
from core.signals.inouts import balance_changed
from exchange.notifications import balance_notificator


@receiver(post_save, sender=WithdrawalRequest)
def create_wallet_history_item_withdrawal_request(sender, instance, created, **kwargs):
    if instance.transaction is not None:
        create_or_update_wallet_history_item_from_transaction(instance.transaction)


@receiver(post_save, sender=WalletTransactions)
def create_wallet_history_item_wallet_transaction(sender, instance: WalletTransactions, created, **kwargs):
    # @TODO check related model, except RelatedObjectDoesNotExist
    try:
        if instance.transaction is not None and instance.status not in [WalletTransactions.STATUS_REVERTED, ]:
            create_or_update_wallet_history_item_from_transaction(instance.transaction)
    except Transaction.DoesNotExist:
        pass


@receiver(post_save, sender=PayGateTopup)
def create_wallet_history_item_paygate_topup(sender, instance: PayGateTopup, created, **kwargs):
    if instance.tx is not None and instance.status not in [PayGateTopup.STATUS_REVERTED, ]:
        create_or_update_wallet_history_item_from_transaction(instance.tx)


@receiver(balance_changed, sender=BalanceManager)
def on_balance_changed(sender, user_id, **kwargs):
    balance_notificator.add_data(user_id=user_id)