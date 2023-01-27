import datetime

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # 'core.auth.token_auth.ExpiringTokenAuthentication',
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    'PAGE_SIZE': 5,
    # 'DATETIME_FORMAT': '%s',
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'DEFAULT_RENDERER_CLASSES': (
        'lib.json_encoder.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'COERCE_DECIMAL_TO_STRING': False,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '5/second',
        'user': '5/second'
    },
    'EXCEPTION_HANDLER': 'lib.utils.exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

REST_AUTH_SERIALIZERS = {
    'USER_DETAILS_SERIALIZER': 'core.serializers.auth.UserSerializer',
    'PASSWORD_RESET_SERIALIZER': 'core.serializers.auth.PasswordResetSerializer',
    'LOGIN_SERIALIZER': 'core.serializers.auth.LoginSerializer',
    'PASSWORD_CHANGE_SERIALIZER': 'core.serializers.auth.PasswdChangeSerializer',
    'PASSWORD_RESET_CONFIRM_SERIALIZER': 'core.serializers.auth.PasswordResetConfirmSerializer',
    # 'TOKEN_SERIALIZER': 'core.serializers.auth.TokenSerializer',
    'JWT_SERIALIZER': 'core.serializers.auth.OurJWTSerializer',
}

JWT_AUTH = {
    'JWT_ENCODE_HANDLER':
    'rest_framework_jwt.utils.jwt_encode_handler',

    'JWT_DECODE_HANDLER':
    'rest_framework_jwt.utils.jwt_decode_handler',

    'JWT_PAYLOAD_HANDLER':
    'core.utils.auth.our_jwt_payload_handler',

    'JWT_PAYLOAD_GET_USER_ID_HANDLER':
    'rest_framework_jwt.utils.jwt_get_user_id_from_payload_handler',

    'JWT_RESPONSE_PAYLOAD_HANDLER':
    'rest_framework_jwt.utils.jwt_response_payload_handler',

    'JWT_AUTH_HEADER_PREFIX': 'Token',
    'JWT_ALGORITHM': 'HS512',

}

REST_USE_JWT = True
JWT_AUTH_COOKIE = 'jwt_auth_token'
JWT_EXPIRATION_DELTA = datetime.timedelta(minutes=60)
