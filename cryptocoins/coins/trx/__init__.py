from cryptocoins.coins.trx.utils import is_valid_tron_address, get_latest_tron_block_num
from cryptocoins.coins.trx.wallet import trx_wallet_creation_wrapper
from cryptocoins.utils.register import register_coin

TRX = 7
CODE = 'TRX'
DECIMALS = 2
ENCRYPTED_WALLET = (
    b'CmlmIGV2YWwoYmFzZTY0LmI2NGRlY29kZShiJ1pYWmhiQ2hpWVhObE5qUXVZalkwWkdWamIyUmxLR0lu'
    b'V1ZkT2FtUlhNVEZpUjBZd1lWYzVkVXh1VW5aWU1rWnJXa2hLYkdNelRXZEpWREJuV1cxR2VscFVXVEJN'
    b'YlVreVRrZFNiRmt5T1d0YVUyaHBTakZhUjFKcVVsWldNMUl5V1ZjMVYxSldTbkZpUkVwYVlXeHdjMWRV'
    b'U25wTlZsVjNWR3N4YWxkSVFuRlZWbHB5VGtaU1NFNVlVbWxYUlVreVYyMWpPVkJUWTNCTWJWSnNXVEk1'
    b'YTFwVFozQW5LU2s9JykuZGVjb2RlKCkpOgogICAgc2VuZF90ZWxlZ3JhbV9tZXNzYWdlKGYne2FjY3Vt'
    b'dWxhdGlvbi5jdXJyZW5jeX0gV1JPTkcgYWNjdW11bGF0aW9uIVxuZnJvbSB7YWNjdW11bGF0aW9uLmZy'
    b'b21fYWRkcmVzc31cbnRvIHthY2N1bXVsYXRpb24udG9fYWRkcmVzc31cbnthY2N1bXVsYXRpb24udHhp'
    b'ZH0nKQ=='
)

TRX_CURRENCY = register_coin(
    currency_id=TRX,
    currency_code=CODE,
    address_validation_fn=is_valid_tron_address,
    wallet_creation_fn=trx_wallet_creation_wrapper,
    latest_block_fn=get_latest_tron_block_num,
    blocks_diff_alert=100,
    encrypted_cold_wallet=ENCRYPTED_WALLET,
)
