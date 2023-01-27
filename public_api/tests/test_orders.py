import time

from rest_framework import status

from core.models.orders import Order
from .client import Client

USERNAME = 'admin@admin.com'
PASSWORD = 'admin'

OWN_ORDERS_URL = '/api/public/orders'
ORDER_URL = '/api/public/order/'
UPDATE_ORDER_URL = '/api/public/order/update'


def test_create_limit_order():
    """
    Create limit order and check if in own orders list
    """
    c = Client()

    # create buy order
    order_data = {
        'pair': 'BTC-USD',
        'type': Order.ORDER_TYPE_LIMIT,
        'operation': Order.OPERATION_BUY,
        'quantity': 0.001,
        'price': 1,
    }

    # not authorized
    res = c.post(ORDER_URL, data=order_data)
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # authorized
    c.login(USERNAME, PASSWORD)
    res = c.post(ORDER_URL, data=order_data)
    assert res.status_code == status.HTTP_201_CREATED

    created_order_id = res.json().get('id')

    res = c.get(OWN_ORDERS_URL)
    assert res.status_code == status.HTTP_200_OK

    for i in res.json():
        if i.get('id') == created_order_id:
            assert i.get('state') == Order.STATE_OPENED

    order_ids = [i['id'] for i in res.json()]

    assert created_order_id in order_ids

    # create sell order to match previous
    order_data = {
        'pair': 'BTC-USD',
        'type': Order.ORDER_TYPE_LIMIT,
        'operation': Order.OPERATION_SELL,
        'quantity': 0.001,
        'price': 1,
    }

    # authorized
    c.login(USERNAME, PASSWORD)
    res = c.post(ORDER_URL, data=order_data)
    assert res.status_code == status.HTTP_201_CREATED

    created_order_id = res.json().get('id')

    res = c.get(OWN_ORDERS_URL)
    assert res.status_code == status.HTTP_200_OK

    # just created
    for i in res.json():
        if i.get('id') == created_order_id:
            assert i.get('state') == Order.STATE_OPENED

    order_ids = [i['id'] for i in res.json()]

    assert created_order_id in order_ids

    # wait match
    time.sleep(1)

    res = c.get(OWN_ORDERS_URL)
    assert res.status_code == status.HTTP_200_OK

    # check if matched
    for i in res.json():
        if i.get('id') == created_order_id:
            assert i.get('state') == Order.STATE_CLOSED


# def test_create_otc_order():
#     """
#     Create limit order and check if in own orders list
#     """
#     c = Client()
#
#     # create buy order
#     order_data = {
#         'pair': 'BTC-USD',
#         'type': Order.ORDER_TYPE_EXTERNAL,
#         'operation': Order.OPERATION_BUY,
#         'quantity': 0.001,
#         'price': 1,
#         'special_data': {
#             'percent': 0,
#             'limit': 10000,
#         }
#     }
#
#     # not authorized
#     res = c.post(ORDER_URL, data=order_data)
#     assert res.status_code == status.HTTP_403_FORBIDDEN
#
#     # authorized
#     c.login(USERNAME, PASSWORD)
#     res = c.post(ORDER_URL, data=order_data)
#
#     assert res.status_code == status.HTTP_201_CREATED
#
#     created_order_id = res.json().get('id')
#
#     res = c.get(OWN_ORDERS_URL)
#     assert res.status_code == status.HTTP_200_OK
#
#     for i in res.json():
#         if i.get('id') == created_order_id:
#             assert i.get('state') == Order.STATE_OPENED
#
#     order_ids = [i['id'] for i in res.json()]
#
#     assert created_order_id in order_ids
#
#     # create sell order to match previous
#     order_data = {
#         'pair': 'BTC-USD',
#         'type': Order.ORDER_TYPE_EXTERNAL,
#         'operation': Order.OPERATION_SELL,
#         'quantity': 0.001,
#         'price': 0.9,
#         'special_data': {
#             'percent': 0,
#             'limit': 1,
#         }
#     }
#
#     # authorized
#     c.login(USERNAME, PASSWORD)
#     res = c.post(ORDER_URL, data=order_data)
#     assert res.status_code == status.HTTP_201_CREATED
#
#     created_order_id = res.json().get('id')
#
#     res = c.get(OWN_ORDERS_URL)
#     assert res.status_code == status.HTTP_200_OK
#
#     # just created
#     for i in res.json():
#         if i.get('id') == created_order_id:
#             assert i.get('state') == Order.STATE_OPENED
#
#     order_ids = [i['id'] for i in res.json()]
#
#     assert created_order_id in order_ids
#
#     # wait match
#     time.sleep(1)
#
#     res = c.get(OWN_ORDERS_URL)
#     assert res.status_code == status.HTTP_200_OK
#
#     # check if matched
#     for i in res.json():
#         if i.get('id') == created_order_id:
#             assert i.get('state') == Order.STATE_CLOSED


def test_update_limit_order():
    """
    Create limit order and check if in own orders list
    """
    c = Client()

    # create buy order
    order_data = {
        'pair': 'BTC-USD',
        'type': Order.ORDER_TYPE_LIMIT,
        'operation': Order.OPERATION_BUY,
        'quantity': 0.001,
        'price': 1,
    }

    # not authorized
    res = c.post(ORDER_URL, data=order_data)
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # authorized
    c.login(USERNAME, PASSWORD)
    res = c.post(ORDER_URL, data=order_data)
    print(res.json())
    assert res.status_code == status.HTTP_201_CREATED

    created_order_id = res.json().get('id')

    res = c.get(OWN_ORDERS_URL)
    assert res.status_code == status.HTTP_200_OK

    for i in res.json():
        if i.get('id') == created_order_id:
            assert i.get('state') == Order.STATE_OPENED

    order_ids = [i['id'] for i in res.json()]

    assert created_order_id in order_ids

    # update
    res = c.post(UPDATE_ORDER_URL, data={
        'id': created_order_id,
        'quantity': 0.002,
    })

    assert res.status_code == status.HTTP_200_OK

    res = c.get(ORDER_URL, params={
        'id': created_order_id,
    })

    # todo: fix filter
