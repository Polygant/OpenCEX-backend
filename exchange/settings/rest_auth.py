import datetime

REST_AUTH_SERIALIZERS = {
    'USER_DETAILS_SERIALIZER': 'core.serializers.auth.UserSerializer',
    'PASSWORD_RESET_SERIALIZER': 'core.serializers.auth.PasswordResetSerializer',
    'LOGIN_SERIALIZER': 'core.serializers.auth.LoginSerializer',
    'PASSWORD_CHANGE_SERIALIZER': 'core.serializers.auth.PasswdChangeSerializer',
    'PASSWORD_RESET_CONFIRM_SERIALIZER': 'core.serializers.auth.PasswordResetConfirmSerializer',
    # 'TOKEN_SERIALIZER': 'core.serializers.auth.TokenSerializer',
    # 'JWT_SERIALIZER': 'core.serializers.auth.OurJWTSerializer',
}

REST_USE_JWT = True
JWT_AUTH_COOKIE = 'jwt_auth_token'
JWT_AUTH_REFRESH_COOKIE = 'jwt_refresh_token'
JWT_EXPIRATION_DELTA = datetime.timedelta(minutes=60)
REST_AUTH_REGISTER_SERIALIZERS = {
    'REGISTER_SERIALIZER': 'core.serializers.auth.RegisterSerializer'
}

OLD_PASSWORD_FIELD_ENABLED = True
