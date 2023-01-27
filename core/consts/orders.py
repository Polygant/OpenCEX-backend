LIMIT = 0
MARKET = 1
EXTERNAL = 2
EXCHANGE = 3
STOP_LIMIT = 4


# todo: move into model
ORDER_OPENED = 0
ORDER_CLOSED = 1
ORDER_CANCELED = 2
ORDER_REVERT = 3

ORDER_TYPES = {
    LIMIT: 'Limit',
    MARKET: 'Market',
    EXTERNAL: 'External',
    EXCHANGE: 'Exchange',
    STOP_LIMIT: 'Stop limit',
}

ORDER_STATES = {
    ORDER_OPENED: 'Opened',
    ORDER_CLOSED: 'Closed',
    ORDER_CANCELED: 'Canceled',
    ORDER_REVERT: 'Moderated',
}

BUY = 0
SELL = 1

OPERATIONS = {
    BUY: 'Buy',
    SELL: 'Sell'
}
