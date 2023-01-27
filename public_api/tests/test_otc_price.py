from rest_framework import status

# from orders.pairs import pairs_list
from .client import Client


OTC_PRICE_URL = '/api/public/bfxprice'


def test_otc_price():
    c = Client()

    res = c.get(OTC_PRICE_URL)
    assert res.status_code == status.HTTP_200_OK

    assert 'price' in res.json()
