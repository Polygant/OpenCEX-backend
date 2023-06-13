from rest_framework import status

from core.models.inouts.pair import PAIRS_LIST
from .client import Client


PAIRS_URL = '/api/public/pairs'


def test_pairs():
    c = Client()

    res = c.get(PAIRS_URL)
    assert res.status_code == status.HTTP_200_OK

    pairs = res.json().get('pairs')

    assert len(PAIRS_LIST) == len(pairs)
