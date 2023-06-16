import logging

import pyotp
import requests
from binance.client import Client as BinanceClient
from requests.exceptions import ConnectionError

from core.consts.orders import LIMIT
from core.models.inouts.pair import Pair
from lib.helpers import pretty_decimal
from lib.helpers import to_decimal

log = logging.getLogger(__name__)


class BaseHttpSession():
    RETRIES = 5
    SLEEP = 0.01

    def __init__(self, *args, **kwargs):
        self._session = requests.Session()

    def _method_call(self, method_name, *args, **kwargs):
        err = None
        for _ in range(self.RETRIES):
            try:
                method = getattr(self._session, method_name)
                r = method(*args, **kwargs)
                r.raise_for_status()
                return r
            except ConnectionError as e:
                print('EXCEPTION11111111', e, type(e))
                err = e

        raise err

    def post(self, *args, **kwargs):
        return self._method_call('post', *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._method_call('get', *args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs.update({
            'verify': False,
        })
        return self._method_call('delete', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._method_call('put', *args, **kwargs)


class ExchangeClientSession(BaseHttpSession):
    API_PATH = '/api/v1'
    SECRET_CODE = 'toosecrettoknow'

    def __init__(self, base_url, token=None):
        super(ExchangeClientSession, self).__init__()
        self.token = token
        self.base_url = base_url + self.API_PATH
        if self.token:
            self._session.headers['Authorization'] = "Token {}".format(self.token)

    def url(self, url):
        return self.base_url + url

    def set_2fa(self, secret):
        url = self.url('/set2fa/')
        r = self.post(url, json={"secretcode": secret})
        return r.json()

    def disable_2fa(self, secret):
        url = self.url('/remove2fa/')
        r = self.post(url, json={"secretcode": secret})
        return r.json()

    def get_balance(self):
        url = self.url('/balance/')
        r = self.get(url)
        return r.json()['balance']

    def login(self, username, password, secret=None):
        url = self.url('/auth/login/')
        googlecode = ''

        if secret:
            totp = pyotp.TOTP(secret)
            googlecode = totp.now()

        r = self.post(url, json={"username": username, "password": password, 'googlecode': googlecode}, verify=False)
        return r.json()

    def confirm_email(self, key):
        url = self.url('/auth/registration/verify-email/')
        r = self.post(url, json={"key": key})
        return r.json()

    def get_user_details(self):
        url = self.url('/auth/user')
        r = self.get(url)
        return r.json()

    def topup(self, currency, amount):
        url = self.url('/test/topup/{}/'.format(currency))
        self.put(url, json={'amount': amount, 'secret_code': self.SECRET_CODE})

    def withdrawal(self, currency, amount):
        url = self.url('/test/withdrawal/{}/'.format(currency))
        self.put(url, json={'amount': amount, 'target': 'test target', 'secret_code': self.SECRET_CODE})

    def register(self, username, password=None, invite=''):
        url = self.url('/auth/registration/')
        if password is None:
            password = username
        self.post(url, json={'username': username, 'password1': password, 'password2': password, 'invite_code': invite})

    def register_confirm(self, username):
        url = self.url('/auth/botconfirm/')
        self.post(url, json={'email': username})

    def make_order(self, pair, operation, quantity, typ, price=None):
        if typ == LIMIT:
            url = self.url('/orders/')
        else:
            url = self.url('/market/')

        r = self.post(url, json={'pair': pair,
                                 'operation': operation,
                                 'quantity': pretty_decimal(quantity, 8),
                                 'type': typ,
                                 'price': pretty_decimal(price, 8),
                                 }, verify=False)
        return r.json()

    def exchange(self, base, quote, operation, quantity):
        url = self.url('/exchange/')

        r = self.post(url, json={'base_currency': base,
                                 'quote_currency': quote,
                                 'operation': operation,
                                 'quantity': pretty_decimal(quantity, 8),
                                 })

        return r.json()

    def exchange_rate(self, base, quote, operation, quantity):
        url = self.url('/exchange/')

        r = self.put(url, json={'base_currency': base,
                                'quote_currency': quote,
                                'operation': operation,
                                'quantity': pretty_decimal(quantity, 8),
                                })

        return r.json()

    def cancel_order(self, order_id):
        url = self.url('/orders/{}/'.format(order_id))
        self.delete(url)

    def list_orders(self, state=None):
        base = '/orders/?limit=1000'
        if state:
            base += '&state={}'.format(state)
        url = self.url(base)
        r = self.get(url)
        return r.json()

    def iter_orders(self, state=None):
        base = '/orders/?limit=1000'
        if state is not None:
            base += '&state={}'.format(state)
        url = self.url(base)
        while url:
            r = self.get(url)
            r.raise_for_status()
            r = r.json()
            for i in r.get('results', []):
                yield i
            url = r['next']

    def list_pairs(self):
        url = self.url('/pairs/')
        r = self.get(url)
        return r.json()

    def get_pair_price(self, cur1, cur2):
        if cur1 == 'CBC':
            url = 'https://api.coinmarketcap.com/v2/ticker/3199/'
            r = requests.get(url)
            r.raise_for_status()

            cbc_usd_price = r.json()['data']['quotes']['USD']['price']

            if cur2 == 'USD':
                return cbc_usd_price
            else:
                url = 'https://min-api.cryptocompare.com/data/price?fsym=USD&tsyms=' + cur2
                r = requests.get(url)
                r.raise_for_status()

                price_in_cur2 = r.json()[cur2]

                return price_in_cur2 * cbc_usd_price
        elif cur1 == 'BTC' and cur2 == 'USD':
            url = 'https://api.bitfinex.com/v1/pubticker/btcusd'
            r = requests.get(url)
            r.raise_for_status()
            return float(r.json()['last_price'])
        else:
            url = 'https://min-api.cryptocompare.com/data/price?fsym=' + cur1 + '&tsyms=' + cur2
            r = self.get(url)
            return r.json()[cur2]

    def get_pairs_prices(self):
        pairs = Pair.objects.all()
        binance_client = BinanceClient(api_key='', api_secret='')
        # bitstamp_client = BitstampClient()
        binance_pairs_data = {bc['symbol']: bc['price'] for bc in binance_client.get_all_tickers()}
        # bitstamp_pairs_data = bitstamp_client.get_all_tickers()

        pairs_prices = {}
        missing_pairs = []

        for pair in pairs:
            base_code = pair.base.code
            quote_code = pair.quote.code

            pair_exchange_key = f'{base_code}{quote_code}'
            pair_cache_key = f'{pair.base.code}-{pair.quote.code}'
            if pair_exchange_key in binance_pairs_data:
                pairs_prices[pair_cache_key] = to_decimal(binance_pairs_data[pair_exchange_key])
            # elif pair_exchange_key in bitstamp_pairs_data:
            #     pairs_prices[pair_cache_key] = to_decimal(bitstamp_pairs_data[pair_exchange_key])
            else:
                missing_pairs.append(pair)

        return pairs_prices

    def stack(self, pair):
        url = self.url('/stack/{}/'.format(pair))
        r = self.get(url)
        return r.json()
