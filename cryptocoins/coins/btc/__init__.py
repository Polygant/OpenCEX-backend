from cryptocoins.coins.btc.utils import is_valid_btc_address
from cryptocoins.utils.register import register_coin
from cryptocoins.utils.wallet import get_latest_block_id, get_wallet_data

BTC = 1
CODE = 'BTC'
DECIMALS = 8

BTC_CURRENCY = register_coin(
    currency_id=BTC,
    currency_code=CODE,
    address_validation_fn=is_valid_btc_address,
    wallet_creation_fn=get_wallet_data,
    latest_block_fn=get_latest_block_id,
    blocks_diff_alert=1,
)
