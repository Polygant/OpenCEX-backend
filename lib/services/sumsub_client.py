import logging
import time
import hashlib
import hmac


import requests
from lib.cache import PrefixedRedisCache
from exchange.settings.kyc import SUMSUB_SECRET_KEY, SUMSUB_APP_TOKEN

logger = logging.getLogger(__name__)
cache = PrefixedRedisCache.get_cache(prefix='sumsub-app-cache-')


class SumSubClient:
    session = requests.Session()
    HOST = 'https://api.sumsub.com'

    def __init__(self, host=None):
        if host:
            self.HOST = host

    def post(self, url, return_result=True, **kwargs):
        try:
            headers = kwargs.pop('headers', {})
            resp = self.sign_request(requests.Request('POST',
                                                      f'{self.HOST}{url}',
                                                      headers=headers,
                                                      **kwargs))
            response = self.session.send(resp)
            response.raise_for_status()
            if return_result:
                return response.json()
        except Exception:
            logger.error(f'error on {url}: {kwargs}', exc_info=True)
            raise

    def get(self, url, **kwargs):
        try:
            headers = kwargs.pop('headers', {})
            resp = self.sign_request(requests.Request('GET',
                                                      f'{self.HOST}{url}',
                                                      headers=headers,
                                                      **kwargs))
            response = self.session.send(resp)
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.error(f'error on {url}: {kwargs}', exc_info=True)
            raise

    def get_acces_token(self, external_user_id, level_name='basic-kyc-level'):
        params = {
            'userId': external_user_id,
            'ttlInSecs': '600',
            'levelName': level_name}
        headers = {'Content-Type': 'application/json',
                   'Content-Encoding': 'utf-8'
                   }
        resp = self.sign_request(requests.Request('POST', self.HOST + '/resources/accessTokens',
                                                  params=params,
                                                  headers=headers))
        response = self.session.send(resp)

        return response.json()

    def sign_request(self, request):
        prepared_request = request.prepare()
        now = int(time.time())
        method = request.method.upper()
        path_url = prepared_request.path_url
        body = b'' if prepared_request.body is None else prepared_request.body
        if isinstance(body, str):
            body = body.encode('utf-8')
        data_to_sign = str(now).encode(
            'utf-8') + method.encode('utf-8') + path_url.encode('utf-8') + body
        signature = hmac.new(
            SUMSUB_SECRET_KEY.encode('utf-8'),
            data_to_sign,
            digestmod=hashlib.sha256
        )
        prepared_request.headers['X-App-Token'] = SUMSUB_APP_TOKEN
        prepared_request.headers['X-App-Access-Ts'] = str(now)
        prepared_request.headers['X-App-Access-Sig'] = signature.hexdigest()
        return prepared_request

    def get_applicant_data(self, applicantId):
        return self.get(f'/resources/applicants/{applicantId}')

    def get_applicant_doc_status(self, applicantId):
        return self.get(
            f'/resources/applicants/{applicantId}/requiredIdDocsStatus')

    def get_image(self, inspectionId, imageId):
        return self.get(
            f'/resources/inspections/{inspectionId}/resources/{imageId}')
