import binascii
import datetime
import decimal
import hashlib
import hmac
import itertools
import logging
import math
import time
from decimal import Decimal, ROUND_DOWN, Context, localcontext
from typing import Union

from Crypto import Random
from django.forms import model_to_dict
from django.utils import timezone

BOT_RE = "^bot[0-9]+@bot.com$"

log = logging.getLogger(__name__)


def dt_from_js(dt):
    return datetime.datetime.fromtimestamp(dt / 1000, tz=timezone.utc)


def remove_exponent(d) -> Decimal:
    return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()


def round_down(value, decimals):
    with localcontext() as ctx:
        d = to_decimal(value)
        ctx.rounding = ROUND_DOWN
        return round(d, decimals)


def to_decimal(value, decimal_places: int = 16) -> Decimal:
    """
    Convert to decimal with rounding down
    """
    return Decimal(str(value)).quantize(Decimal('.00000001'), rounding=ROUND_DOWN, context=Context(prec=100))


def pretty_decimal(number, digits=4) -> str:
    """ returns formatted decimal number as string """
    if number is None:
        return None
    number = to_decimal(number)
    return f'{{:0.{digits}f}}'.format(number).rstrip('0').rstrip('.')


def to_decimal_pretty(number, digits, remove_exp=True):
    res = to_decimal(pretty_decimal(number, digits=digits))
    return remove_exponent(res) if remove_exp else res


def decimalize(val: Union[Decimal, str, int, float]) -> Decimal:
    return Decimal(str(val))


def round_by_precision(x, base, is_bid=True):
    x = decimalize(x)
    base = decimalize(base)
    decimals = decimalize(10 ** base.as_tuple().exponent)
    rounding = decimal.ROUND_FLOOR if is_bid else decimal.ROUND_CEILING
    if base > 1:
        return base*decimalize(x/base).quantize(decimals, rounding=rounding)
    return decimalize(base * decimalize(x / base)).quantize(decimals, rounding=rounding)


def normalize_data(data):
    """
    Cast specific data types to simple representation
    """
    if isinstance(data, dict):
        for key, value in data.items():
            # decimal
            if isinstance(value, Decimal):
                data[key] = float(value)

            # recursive processing
            if isinstance(value, (dict, list)):
                data[key] = normalize_data(value)

    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(normalize_data(item))

        data = result

    # decimal
    elif isinstance(data, Decimal):
        data = float(data)

    return data


def chunked(iterable, n, fill_value=None):
    args = [iter(iterable)] * n
    for i in itertools.zip_longest(fillvalue=fill_value, *args):
        if tuple(i)[-1] == fill_value:
            yield tuple(v for v in i if v != fill_value)
        else:
            yield i


def make_hmac_signature_headers(api_key, secret_key):
    nonce = str(int(time.time()))
    message = api_key + nonce
    signature = hmac.new(
        secret_key.encode(),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()
    headers = {
        'APIKEY': api_key,
        'SIGNATURE': signature,
        'NONCE': nonce
    }
    return headers


def calc_absolute_percent_difference(num1, num2):
    percent_diff = (max(num1, num2) - min(num1, num2)) / min(num1, num2) * 100
    return percent_diff


def calc_percent(num1, num2):
    num1 = to_decimal(num1)
    num2 = to_decimal(num2)
    return (num2 - num1)/num1 * 100


def calc_relative_percent_difference(num1, num2):
    return math.fabs(calc_percent(num1, num2))


def copy_instance(instance, model):
    instance_data = model_to_dict(instance, fields=[
        field.name for field in instance._meta.fields
        if field.name != 'id'
    ])

    if instance_data.get('user') is not None:
        instance_data['user_id'] = instance_data.get('user')
        del instance_data['user']

    return model(**instance_data)


def get_iso_dt():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+'Z'


def generate_unique_token(length=20):
    return binascii.hexlify(Random.new().read(length)).decode('utf-8').upper()


def find_similar_entry_by_field(field_name, field_value, entries_list):
    for i, entry in enumerate(entries_list):
        if entry.get(field_name) == field_value:
            return i, entry
    return None, None


def sat_to_btc(sat):
    return to_decimal(sat) / to_decimal(10**8)
