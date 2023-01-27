from exchange.settings import env

IS_SMS_ENABLED = env('IS_SMS_ENABLED', default=False)

TWILIO = {
    'ENABLED':  env('TWILIO_ENABLED', default=False),
    'ACCOUNT_SID': env('TWILIO_ACCOUNT_SID'),
    'AUTH_TOKEN': env('TWILIO_AUTH_TOKEN'),
    'VERIFY_SID': env('TWILIO_VERIFY_SID'),
    'PHONE_FROM': env('TWILIO_PHONE'),
}
