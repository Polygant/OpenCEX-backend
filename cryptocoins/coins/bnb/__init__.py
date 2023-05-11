from cryptocoins.coins.bnb.connection import get_w3_connection
from cryptocoins.coins.bnb.wallet import bnb_wallet_creation_wrapper
from cryptocoins.coins.bnb.wallet import is_valid_bnb_address
from cryptocoins.utils.register import register_coin


BNB = 17
CODE = 'BNB'
DECIMALS = 8

BNB_CURRENCY = register_coin(
    currency_id=BNB,
    currency_code=CODE,
    address_validation_fn=is_valid_bnb_address,
    wallet_creation_fn=bnb_wallet_creation_wrapper,
    latest_block_fn=lambda currency: get_w3_connection().eth.get_block_number(),
    blocks_diff_alert=100,
)
