from corsheaders.defaults import default_headers


CORS_ORIGIN_ALLOW_ALL = True

CORS_ALLOW_HEADERS = default_headers + (
    'APIKEY',
    'SIGNATURE',
    'NONCE',
    'X_KEY',
    'X_NONCE',
    'X_SIGN',
    'x-api-lang',
)

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
