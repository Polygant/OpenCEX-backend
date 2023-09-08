from core.currency import CoinParams
from cryptocoins.coins.matic.connection import get_w3_polygon_connection
from cryptocoins.coins.matic.consts import MATIC, CODE
from cryptocoins.coins.matic.wallet import matic_wallet_creation_wrapper, is_valid_matic_address
from cryptocoins.utils.register import register_coin

w3 = get_w3_polygon_connection()

MATIC_CURRENCY = register_coin(
    currency_id=MATIC,
    currency_code=CODE,
    address_validation_fn=is_valid_matic_address,
    wallet_creation_fn=matic_wallet_creation_wrapper,
    latest_block_fn=lambda currency: w3.eth.get_block_number(),
    blocks_diff_alert=100,
)
