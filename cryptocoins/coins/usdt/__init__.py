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
}
USDT_CURRENCY = register_token(USDT, CODE, BLOCKCHAINS)
