from lib.helpers import to_decimal
from core.consts.orders import BUY, SELL
from core.orderbook.helpers import get_stack_by_pair
from core.orderbook.book import PreMatch
from core.models.inouts.pair import Pair


def prepare_market_data(user, data, serializer):
    data['price'] = to_decimal(data.get('price', 0))

    serializer_item = serializer(data=data)
    serializer_item.is_valid(raise_exception=True)
    data = serializer_item.data
    data['pair_name'] = Pair.get(data['pair']).code
    data['pair_id'] = Pair.get(data['pair']).id
    data['user_id'] = user.id

    return data


def market_cost_and_price(pair_name, operation, quantity):
    from core.views.orders import stack_iter
    stack = get_stack_by_pair(pair_name)
    stack = stack.get('sells', []) if operation == BUY else stack.get('buys', [])
    cost, price = PreMatch(stack_iter(stack)).find_cost_and_price(quantity)
    return cost, price


def get_cost_and_price(user, data, serializer):
    from core.views.orders import stack_iter
    # just find price
    data = prepare_market_data(user, data, serializer)
    target_qty = None
    orders = []
    cost, price = None, None

    data['quantity'] = to_decimal(data.get('quantity', 0))

    stack = get_stack_by_pair(data['pair_name'])
    if data['strict_pair']:
        cost, price = market_cost_and_price(data['pair_name'], data['operation'], data['quantity']) or 0
        cost = cost or 0
        price = cost / data['quantity']
    else:
        stack = stack.get('sells', []) if data['operation'] == SELL else stack.get('buys', [])
        if data['quantity'] > 0:
            target_qty, _, orders = PreMatch(stack_iter(stack)).find_qty_and_price(data['quantity'])
        if target_qty:
            cost = sum((i[1] for i in orders))
            price = cost / data['quantity']
        elif data.get('quantity_alt'):
            cost, price = PreMatch(stack_iter(stack)).find_cost_and_price(data['quantity_alt'])

    return cost, price
