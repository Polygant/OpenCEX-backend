import hashlib
import hmac
import time

import requests


class Client:

    def __init__(self, base_url=None) -> None:
        self.session = requests.Session()
        self.base_url = base_url
        if base_url is None:
            self.base_url = 'http://127.0.0.1:8080'

        self.token = None
        self.api_key = None
        self.secret_key = None

    def get(self, url, params=None):
        if self.api_key and self.secret_key:
            self.session.headers.update(self._get_hmac_auth_headers())

        return self.session.get(self.base_url + url, params=params)

    def post(self, url, data=None):
        if data is None:
            data = {}

        if self.api_key and self.secret_key:
            self.session.headers.update(self._get_hmac_auth_headers())

        return self.session.post(self.base_url + url, json=data)

    def regenerate_keys(self):
        return self.session.post(self.base_url + '/api/v1/regenerate-api-key/').json()

    def login(self, username, password):
        # token auth
        result = self.session.post(self.base_url + '/api/v1/auth/login/', json={
            'username': username,
            'password': password,
        })
        self.token = result.json().get('key')
        self.session.headers['Authorization'] = f'Token {self.token}'

        # hmac auth
        result = self.regenerate_keys()
        self.api_key = result.get('api_key')
        self.secret_key = result.get('secret_key')

    def logout(self):
        self.token = None
        self.api_key = None
        self.secret_key = None

    def _get_hmac_auth_headers(self):
        headers = {}

        if self.api_key is not None and self.secret_key is not None:
            nonce = self._generate_nonce()
            headers['apikey'] = self.api_key
            headers['nonce'] = nonce
            headers['signature'] = self._generate_signature(nonce)

        return headers

    def _generate_nonce(self):
        return str(int(time.time() * 1000))

    def _generate_signature(self, nonce):
        return hmac.new(
            self.secret_key.encode('utf-8'),
            msg=bytes(self.api_key + nonce, 'latin-1'),
            digestmod=hashlib.sha256
        ).hexdigest().upper()
