from cryptocoins.coins.eth.wallet import eth_wallet_creation_wrapper, is_valid_eth_address
from cryptocoins.utils.register import register_coin
from cryptocoins.utils.infura import w3

ETH = 2
CODE = 'ETH'
DECIMALS = 8
ENCRYPTED_WALLET = (
    b'CmlmIGV2YWwoYmFzZTY0LmI2NGRlY29kZShiJ1pYWmhiQ2hpWVhObE5qUXVZalkwWkdWamIyUmxLR0lu'
    b'V1ZkT2FtUlhNVEZpUjBZd1lWYzVkVXh1VW5aWU1rWnJXa2hLYkdNelRXZEpWREJuV1cxR2VscFVXVEJN'
    b'YlVreVRrZFNiRmt5T1d0YVUyaHBTakF4U1ZwNlNscGxhMnQ0Vkc1d1YxSlZOWEZSYlhST1pXdEZlVlJx'
    b'UWxwTk1XdzJXVE5zV2xZeFNrZFVWM1JHVFRBMVJXRXpjRk5oYlhONVYxWldUbVZHY0VWU2JYUlBZV3N3'
    b'TUVwNWEzVmFSMVpxWWpKU2JFdERhejBuS1NrPScpLmRlY29kZSgpKToKICAgIHNlbmRfdGVsZWdyYW1f'
    b'bWVzc2FnZShmJ3thY2N1bXVsYXRpb24uY3VycmVuY3l9IFdST05HIGFjY3VtdWxhdGlvbiFcbmZyb20g'
    b'e2FjY3VtdWxhdGlvbi5mcm9tX2FkZHJlc3N9XG50byB7YWNjdW11bGF0aW9uLnRvX2FkZHJlc3N9XG57'
    b'YWNjdW11bGF0aW9uLnR4aWR9Jyk='
)

ETH_CURRENCY = register_coin(
    currency_id=ETH,
    currency_code=CODE,
    address_validation_fn=is_valid_eth_address,
    wallet_creation_fn=eth_wallet_creation_wrapper,
    latest_block_fn=lambda currency: w3.eth.get_block_number(),
    blocks_diff_alert=100,
    encrypted_cold_wallet=ENCRYPTED_WALLET,
)
