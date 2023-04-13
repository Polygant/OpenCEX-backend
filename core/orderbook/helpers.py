import json
from itertools import chain

from django.core.cache import cache

from core.pairs import Pair
from lib.helpers import decimalize, round_by_precision


def get_stack_by_pair(pair, precision=None):
    pair = Pair.get(pair)
    pair = pair.code.upper()
    key = f'stack:{pair}'
    if precision:
        key = f'stack:{pair}:{precision}'
    try:
        data = cache.get(key)
        if data:
            data = json.loads(data)
        data = data or {}

    except Exception:
        data = {}

    return data


def mark_self_stack(stack, user_id):
    for i in chain(stack.get('buys', []), stack.get('sells', [])):
        if 'user_id' in i:
            i['owner'] = i['user_id'] == user_id

        if 'user_ids' in i:
            i['owners'] = i['user_ids']
            i['owner'] = user_id in i['user_ids']

        # del i['user_id']
    return stack


def group_by_precision(pair_code, stack_data):
    res = {}
    buys = stack_data['buys']
    sells = stack_data['sells']

    from core.models import PairSettings
    stack_precisions = PairSettings.get_stack_precisions_by_pair(pair_code)

    for precision in stack_precisions:
        stack_data_copy = stack_data.copy()
        new_buys = {}
        new_sells = {}

        for buy in buys:
            recalculate_stack_quantity(new_buys, buy, precision, is_bid=True)

        for sell in sells:
            recalculate_stack_quantity(new_sells, sell, precision, is_bid=False)

        stack_data_copy['buys'] = sorted(new_buys.values(), key=lambda k: k['price'])
        stack_data_copy['sells'] = sorted(new_sells.values(), key=lambda k: k['price'])

        stack_data_copy['buys'] = sorted(recalculate_depth(stack_data_copy['buys']),
                                         key=lambda k: k['price'], reverse=True)
        stack_data_copy['sells'] = sorted(recalculate_depth(stack_data_copy['sells']),
                                          key=lambda k: k['price'], reverse=True)
        res[precision] = stack_data_copy
    return res


def recalculate_depth(data_list):
    depth = 0
    result = []
    for i in data_list:
        depth += decimalize(i['quantity'])
        i['depth'] = depth
        result.append(i)
    return result


def recalculate_stack_quantity(new_data, current_value_dict, precision, is_bid):
    new_price = round_by_precision(current_value_dict['price'], precision, is_bid=is_bid)
    if new_price in new_data:
        updated = {
            'quantity': decimalize(new_data[new_price]['quantity']) + decimalize(current_value_dict['quantity']),
            'user_ids': new_data[new_price]['user_ids'] + [current_value_dict['user_id']],
            'ids': new_data[new_price]['ids'] + [current_value_dict['id']],
            'timestamp': current_value_dict['timestamp'],
        }
        new_data[new_price].update(updated)
    else:
        new_data[new_price] = {
            'price': new_price,
            'quantity': decimalize(current_value_dict['quantity']),
            'user_ids': [current_value_dict['user_id']],
            'timestamp': current_value_dict['timestamp'],
            'ids': [current_value_dict['id']]
        }
