import datetime
import logging

import requests
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from lib.helpers import to_decimal
from lib.utils import memcache_lock
from .bot import Bot
from .helpers import get_ranged_random
from .models import BotConfig
log = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True)
def check_bot(self, bot_id):
    lock_id = f'checking_bot_{bot_id}'
    with memcache_lock(lock_id, lock_id) as acquired:
        if acquired:
            bot_config = BotConfig.objects.get(id=bot_id)
            log.info('Launching bot %s', bot_config)

            if bot_config.loop_period_random:
                period = int(get_ranged_random(bot_config.min_period, bot_config.max_period))
            else:
                period = bot_config.loop_period
            bot_config.next_launch = timezone.now() + timezone.timedelta(seconds=period)
            bot_config.save()

            bot = Bot(bot_config=bot_config)
            try:
                bot.run()
                bot_config.stopped = False
                bot_config.save()
            except requests.exceptions.HTTPError as ex:
                log.warning('Status %s, content: %s', ex.response.status_code, ex.response.content)
                if ex.response.status_code != 400:
                    log.exception('Error occurred, retrying')
                    raise self.retry(countdown=1, max_retries=1)


@shared_task
def check_bots():
    disabled_bots = BotConfig.objects.filter(
        enabled=False,
        stopped=False
    )

    for bot_config in disabled_bots:
        bot = Bot(bot_config=bot_config)
        bot.cancel_all_orders()
        bot_config.stopped = True
        bot_config.save()

    bot_configs = BotConfig.objects.filter(
        # user__username__iregex=BOT_USERNAME_RE,
        enabled=True,
        next_launch__lte=timezone.now(),
    )

    log.info('Selected configs count: %s', bot_configs.count())

    for bot_config in bot_configs:
        check_bot.apply_async([bot_config.id])
