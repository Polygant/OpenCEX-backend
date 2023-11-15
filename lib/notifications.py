import asyncio

import telegram
from django.conf import settings
import logging

log = logging.getLogger(__name__)


def send_telegram_message(message, logger=None, chat_id=None, bot_token=None):
    logger = logger or log
    try:
        token = bot_token or settings.TELEGRAM_BOT_TOKEN
        chat_id = chat_id or settings.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            return

        bot = telegram.Bot(token=token)
        asyncio.run(
            bot.send_message(chat_id, f'Instance: {settings.INSTANCE_NAME}\n' + message)
        )
    except Exception as e:
        logger.error(e)
