from exchange.settings import env

BOTS_API_BASE_URL = env('BOTS_API_BASE_URL')
BOT_PASSWORD = env('BOT_PASSWORD', default='123456')
