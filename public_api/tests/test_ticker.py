from rest_framework import status

from core.models.inouts.pair import PAIRS_LIST
from .client import Client


TICKER_URL = '/api/public/ticker'


def test_ticker():
    c = Client()

    res = c.get(TICKER_URL)
    assert res.status_code == status.HTTP_200_OK

    for pair in PAIRS_LIST:
        assert pair[1] in res.json()
