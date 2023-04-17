import requests
import random
from lib.helpers import to_decimal


def get_pair_price(pair):
    pass


def get_ranged_random(min, max):
    return to_decimal(random.uniform(float(min), float(max)))


class BaseHttpSession():
    RETRIES = 5
    SLEEP = 0.01

    def __init__(self, url, *args, **kwargs):
        self._session = requests.Session()
        self.url = url

    def _make_url(self, url):
        return self.url + url

    def _method_call(self, method_name, url, *args, **kwargs):
        url = self._make_url(url)
        err = None
        for _ in range(self.RETRIES):
            try:
                method = getattr(self._session, method_name)
                r = method(url, *args, **kwargs)
                r.raise_for_status()
                return r
            except ConnectionError as e:
                print('EXCEPTION', e, type(e))
                err = e
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    print(e.response.text)
                err = e

        raise err

    def post(self, url, *args, **kwargs):
        return self._method_call('post', url,  *args, **kwargs)

    def get(self, url, *args, **kwargs):
        return self._method_call('get', url, *args, **kwargs)

    def delete(self, url, *args, **kwargs):
        kwargs.update({
            'verify': False,
        })
        return self._method_call('delete', url, *args, **kwargs)

    def put(self, url, *args, **kwargs):
        return self._method_call('put', url, *args, **kwargs)
