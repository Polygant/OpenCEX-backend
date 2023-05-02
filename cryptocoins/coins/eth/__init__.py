from cryptocoins.coins.eth.wallet import eth_wallet_creation_wrapper, is_valid_eth_address
from cryptocoins.utils.register import register_coin
from cryptocoins.utils.infura import w3

ETH = 2
CODE = 'ETH'
DECIMALS = 8

ETH_CURRENCY = register_coin(
    currency_id=ETH,
    currency_code=CODE,
    address_validation_fn=is_valid_eth_address,
    wallet_creation_fn=eth_wallet_creation_wrapper,
    latest_block_fn=lambda currency: w3.eth.get_block_number(),
    blocks_diff_alert=100,
)
