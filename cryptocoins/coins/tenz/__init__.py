from cryptocoins.coins.tenz.utils import is_valid_tenz_address
from cryptocoins.utils.register import register_coin
from cryptocoins.utils.wallet import get_latest_block_id, get_wallet_data

TENZ = 29
CODE = 'TENZ'
DECIMALS = 8

TENZ_CURRENCY = register_coin(
    currency_id=TENZ,
    currency_code=CODE,
    address_validation_fn=is_valid_tenz_address,
    wallet_creation_fn=get_wallet_data,
    latest_block_fn=get_latest_block_id,
    blocks_diff_alert=1,
) 