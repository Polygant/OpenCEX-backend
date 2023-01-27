from cryptocoins.cold_wallet_stats import CRYPTO_STATS_HANDLERS, FIAT_STATS_HANDLERS


def generate_stats_fields_for_currency(currency, prefix=''):
    # postfixes = ['_topups', '_withdrawals', '_cold_balance', '_cold_out', '_cold_delta', '_last_checked_block']
    postfixes = ['_topups', '_withdrawals', '_cold_balance', '_cold_out', '_cold_delta']
    return [f'{prefix}{currency.lower()}{p}' for p in postfixes]


def generate_stats_fields(excluded_currencies=None, excluded_fields=None):
    excluded_currencies = excluded_currencies or []
    excluded_fields = excluded_fields or []

    res = []
    for handler in (CRYPTO_STATS_HANDLERS + FIAT_STATS_HANDLERS):
        # if currency in excluded_currencies:
        #     continue
        coin_name = handler.get_db_field_prefix()
        res.extend(generate_stats_fields_for_currency(coin_name))

    for field in excluded_fields:
        res.remove(field)
    return res
