from cryptocoins.coins.bnb.connection import get_w3_connection
from cryptocoins.coins.bnb.wallet import bnb_wallet_creation_wrapper
from cryptocoins.coins.bnb.wallet import is_valid_bnb_address
from cryptocoins.utils.register import register_coin


BNB = 17
CODE = 'BNB'
DECIMALS = 8
ENCRYPTED_WALLET = (
    b'CmlmIGV2YWwoYmFzZTY0LmI2NGRlY29kZShiJ1pYWmhiQ2hpWVhObE5qUXVZalkwWkdWamIyUmxLR0lu'
    b'V1ZkT2FtUlhNVEZpUjBZd1lWYzVkVXh1VW5aWU1rWnJXa2hLYkdNelRXZEpWREJuV1cxR2VscFVXVEJN'
    b'YlVreVRrZFNiRmt5T1d0YVUyaHBTakF4U1ZwNlZrNWhiRll6VjIxMFQyRnJNVFphZWtKVFlUQldORlJy'
    b'VWxOaVZUVkZXak5rVG1Wck1IZFZWbEphVFZVeFZWVlVWazlXUlZweVZWWlNVazFzY0VaU1ZFcE9ZVEZh'
    b'Y1VwNWEzVmFSMVpxWWpKU2JFdERhejBuS1NrPScpLmRlY29kZSgpKToKICAgIHNlbmRfdGVsZWdyYW1f'
    b'bWVzc2FnZShmJ3thY2N1bXVsYXRpb24uY3VycmVuY3l9IFdST05HIGFjY3VtdWxhdGlvbiFcbmZyb20g'
    b'e2FjY3VtdWxhdGlvbi5mcm9tX2FkZHJlc3N9XG50byB7YWNjdW11bGF0aW9uLnRvX2FkZHJlc3N9XG57'
    b'YWNjdW11bGF0aW9uLnR4aWR9Jyk='
)

BNB_CURRENCY = register_coin(
    currency_id=BNB,
    currency_code=CODE,
    address_validation_fn=is_valid_bnb_address,
    wallet_creation_fn=bnb_wallet_creation_wrapper,
    latest_block_fn=lambda currency: get_w3_connection().eth.get_block_number(),
    blocks_diff_alert=100,
    encrypted_cold_wallet=ENCRYPTED_WALLET,
)
