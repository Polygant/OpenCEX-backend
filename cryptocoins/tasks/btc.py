import logging

from bitcoinrpc.authproxy import AuthServiceProxy
from celery import shared_task
from django.conf import settings

from cryptocoins.cache import sat_per_byte_cache
from lib.helpers import to_decimal

log = logging.getLogger(__name__)

def get_fees_from_tx(tx):
    fee = tx['fees']
    if type(fee) is dict:
        fee = fee['base']
    return fee

@shared_task
def cache_bitcoin_sat_per_byte(logger=None):
    """Calculates bitcoin sat/b value using mempool info and caches it"""
    logger = logger or log
    config = 'http://{username}:{password}@{host}:{port}'.format(**settings.NODES_CONFIG['btc'])
    rpc = AuthServiceProxy(config, timeout=settings.SAT_PER_BYTES_UPDATE_PERIOD)
    s_p_b = 30  # minimal

    try:
        txs = list(rpc.getrawmempool(True).values())
        #  сортируем транзакции по sat/b
        spb_list = sorted(
            list([get_fees_from_tx(tx) * 10 ** 8 / tx['vsize'] for tx in txs]),
            reverse=True
        )
        total_txs_count = len(spb_list)
        # Достаем 1500е значение или последнее
        if 0 < total_txs_count <= 1500:
            s_p_b = spb_list[-1]
        elif total_txs_count > 1500:
            s_p_b = spb_list[1500]
        s_p_b = round(to_decimal(s_p_b) * to_decimal(settings.SAT_PER_BYTES_RATIO))
    except Exception as e:
        logger.exception('Can\'t calculate satoshi per byte')

    if s_p_b < settings.SAT_PER_BYTES_MIN_LIMIT:
        s_p_b = settings.SAT_PER_BYTES_MIN_LIMIT

    if s_p_b > settings.SAT_PER_BYTES_MAX_LIMIT:
        s_p_b = settings.SAT_PER_BYTES_MAX_LIMIT

    sat_per_byte_cache.set('bitcoin', s_p_b)
