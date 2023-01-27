import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


# TODO refactor
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


class CryptocompareClient(BaseHttpSession):
    BASE_PATH = 'https://min-api.cryptocompare.com/data'

    def __init__(self):
        super(CryptocompareClient, self).__init__()
        self.api_key = settings.CRYPTOCOMPARE_API_KEY

    def url(self, url):
        return self.BASE_PATH + url

    def get_multi_prices(self, in_currencies, out_currencies):
        cc_data = {}
        try:
            url = self.url('/pricemulti')
            params = {
                'fsyms': in_currencies,
                'tsyms': out_currencies
            }
            if self.api_key:
                params['api_key'] = self.api_key

            r = self.get(url, params=params, timeout=5)
            # r.raise_for_status()
            cc_data = r.json()
        except Exception:
            log.exception('Can\'t fetch data from cryptocompare.com')

        return cc_data