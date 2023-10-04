import logging

from django.conf import settings

from cryptocoins.coins.eth.ethereum import ethereum_manager

log = logging.getLogger(__name__)


def send_tx(from_address, to_address, amount=None):
    address = from_address

    amount_wei = ethereum_manager.get_balance_in_base_denomination(address)
    amount = ethereum_manager.get_amount_from_base_denomination(amount_wei)
    log.info('Accumulation ETH from: %s; Balance: %s',address, amount,)

    # we want to process our tx faster
    gas_price = ethereum_manager.gas_price_cache.get_price()
    gas_amount = gas_price * settings.ETH_TX_GAS
    withdrawal_amount = amount_wei - gas_amount

    # in debug mode values can be very small
    if withdrawal_amount <= 0:
        log.error('ETH withdrawal amount invalid: %s', ethereum_manager.get_amount_from_base_denomination(withdrawal_amount))
        return

    # prepare tx
    wallet = ethereum_manager.get_user_wallet('ETH', address)
    nonce = ethereum_manager.client.eth.getTransactionCount(address)

    tx_hash = ethereum_manager.send_tx(
        private_key=wallet.private_key,
        to_address=to_address,
        amount=withdrawal_amount,
        nonce=nonce,
        gasPrice=gas_price,
    )

    if not tx_hash:
        log.error('Unable to send accumulation TX')
        return

    log.info('Accumulation TX %s sent from %s to %s', tx_hash.hex(), wallet.address, to_address)
