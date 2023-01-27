from collections import defaultdict
from decimal import Decimal

from lib.helpers import to_decimal


def format_scorechain_response(signals_data, score_percent_key='percent'):
    """
    Translate ScoreChain relations into signals

    "relationships": [
      {
        "type": "exchange",
        "label": "string",
        "address": "string",
        "value": 0.42,
        "percent": 13,
        "scx": 37
      },
      {
        "type": "Miners",
        "label": "string",
        "address": "string",
        "value": 0.42,
        "percent": 24,
        "scx": 37
      },
    ]

    [ exchange, MIXING, Miners, Neutral, OFAC Sanction list,
    ToBig, cloudmining, darkweb, gambling, miners, mixing,
    scammer, service ]
    """
    default_signals = {
        'dark_market': 0,
        'dark_service': 0,
        'exchange': 0,
        'trusted_exchange': 0,
        'gambling': 0,
        'illegal_service': 0,
        'marketplace': 0,
        'miner': 0,
        'mixer': 0,
        'payment': 0,
        'ransom': 0,
        'scam': 0,
        'stolen_coins': 0,
        'wallet': 0,
        'service': 0,
        'neutral': 0,
        'sanction': 0,
        'unknown': 0,
    }
    default_data = defaultdict(Decimal)

    for relationship in signals_data:
        value = to_decimal(relationship[score_percent_key]) / 100
        key = get_signal_type_from_response(relationship['type'])
        default_data[key] += value

    result = dict(default_signals)
    result.update(default_data)
    result = {k: str(val) for k, val in result.items()}
    return result


def get_signal_type_from_response(rel_type: str):
    rel_type = rel_type.lower()
    # map types
    if rel_type == 'darkweb':
        key = 'dark_market'
    elif rel_type == 'dex':
        key = 'dex'
    elif rel_type == 'exchange':
        key = 'trusted_exchange'
    elif rel_type == 'gambling':
        key = 'gambling'
    elif rel_type in ('miners', 'cloudmining'):
        key = 'miner'
    elif rel_type in ('mixing', 'mixing service',):
        key = 'mixer'
    elif rel_type == 'scammer':
        key = 'scam'
    elif rel_type == 'service':
        key = 'service'
    elif rel_type == 'neutral':
        key = 'neutral'
    elif rel_type == 'ofac sanction list':
        key = 'sanction'
    else:
        key = 'unknown'
    return key
