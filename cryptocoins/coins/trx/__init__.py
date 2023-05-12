from cryptocoins.coins.trx.utils import is_valid_tron_address, get_latest_tron_block_num
from cryptocoins.coins.trx.wallet import trx_wallet_creation_wrapper
from cryptocoins.utils.register import register_coin

TRX = 7
CODE = 'TRX'
DECIMALS = 2

TRX_CURRENCY = register_coin(
    currency_id=TRX,
    currency_code=CODE,
    address_validation_fn=is_valid_tron_address,
    wallet_creation_fn=trx_wallet_creation_wrapper,
    latest_block_fn=get_latest_tron_block_num,
    blocks_diff_alert=100,
)
