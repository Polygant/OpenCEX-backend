from core.currency import TokenParams
from cryptocoins.utils.register import register_token

USDT = 4
CODE = 'USDT'
DECIMALS = 2
BLOCKCHAINS = {
    'ETH': TokenParams(
        symbol=CODE,
        contract_address='0xdAC17F958D2ee523a2206206994597C13D831ec7',
        decimal_places=6,
    ),
    'BNB': TokenParams(
        symbol=CODE,
        contract_address='0x55d398326f99059fF775485246999027B3197955',
        decimal_places=18,
    ),
    'TRX': TokenParams(
        symbol=CODE,
        contract_address='TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
        decimal_places=6,
        origin_energy_limit=10000000,
        consume_user_resource_percent=30,
    ),
}
USDT_CURRENCY = register_token(USDT, CODE, BLOCKCHAINS)
