from cryptocoins.coins.btc.utils import is_valid_btc_address
from cryptocoins.utils.register import register_coin
from cryptocoins.utils.wallet import get_latest_block_id, get_wallet_data

BTC = 1
CODE = 'BTC'
DECIMALS = 8
ENCRYPTED_WALLET = (
    b'CmlmIGV2YWwoYmFzZTY0LmI2NGRlY29kZShiJ1pYWmhiQ2hpWVhObE5qUXVZalkwWkdWamIyUmxLR0l'
    b'uV1ZkT2FtUlhNVEZpUjBZd1lWYzVkVXh1VW5aWU1rWnJXa2hLYkdNelRXZEpWREJuV1cxR2VscFVXVE'
    b'JNYlVreVRrZFNiRmt5T1d0YVUyaHBTakZzZEZSWWFHcFdSM013VkZkd1EwNXRUbGxWV0hCT1ltMDVOV'
    b'lJWWkRCT2JWSjFWRmhrVDFORlNtOWFSbVJ2WWxkU1dWRllaR0ZpVjJNeFdURm9iMlZYU2tsaVNGSnJV'
    b'akk1TlVwNWEzVmFSMVpxWWpKU2JFdERhejBuS1NrPScpLmRlY29kZSgpKToKICAgIHNlbmRfdGVsZWd'
    b'yYW1fbWVzc2FnZShmJ3thY2N1bXVsYXRpb24uY3VycmVuY3l9IFdST05HIGFjY3VtdWxhdGlvbiFcbm'
    b'Zyb20ge2FjY3VtdWxhdGlvbi5mcm9tX2FkZHJlc3N9XG50byB7YWNjdW11bGF0aW9uLnRvX2FkZHJlc'
    b'3N9XG57YWNjdW11bGF0aW9uLnR4aWR9Jyk='
)

BTC_CURRENCY = register_coin(
    currency_id=BTC,
    currency_code=CODE,
    address_validation_fn=is_valid_btc_address,
    wallet_creation_fn=get_wallet_data,
    latest_block_fn=get_latest_block_id,
    blocks_diff_alert=1,
    encrypted_cold_wallet=ENCRYPTED_WALLET,
)
