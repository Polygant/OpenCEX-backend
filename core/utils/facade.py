import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db import ProgrammingError
from django.template.loader import render_to_string
from django.urls.base import reverse
from django.utils.translation import activate

from core.cache import API_CALLBACK_CACHE_KEY
from core.cache import facade_cache
from core.cache import orders_app_cache
from core.models.facade import Profile
from core.models.inouts.pair import Pair

log = logging.getLogger(__name__)
User = get_user_model()

BOT_USERNAME_RE = r'^bot[0-9]+@bot\.com$'
BOT_USERNAME_CMPRE = re.compile(BOT_USERNAME_RE)


def load_api_callback_urls_cache():
    try:
        qs = Profile.objects.filter(
            api_callback_url__isnull=False,
        ).exclude(
            api_callback_url='',
        ).values(
            'user_id',
            'api_callback_url',
        )

        data = {f'{API_CALLBACK_CACHE_KEY}-{i["user_id"]}': i['api_callback_url'] for i in qs}

        orders_app_cache.set_many(data, timeout=None)

    except ProgrammingError:
        # DB is empty (when create test or new setup for example)
        log.debug('Cant load callbacks from empty DB')
        pass


def set_cached_api_callback_url(user_id, callback_url):
    orders_app_cache.set(f'{API_CALLBACK_CACHE_KEY}-{user_id}', callback_url, timeout=None)


def get_cached_api_callback_url(user_id):
    return orders_app_cache.get(f'{API_CALLBACK_CACHE_KEY}-{user_id}')


def is_bot_user(username):
    return bool(BOT_USERNAME_CMPRE.match(username))


def generate_sitemap():
    cache_key = 'sitemap'
    result = facade_cache.get(cache_key)
    if not result:
        # current_language = get_language()

        def make_entry(uri=''):
            url = 'https://' + Site.objects.get_current().domain + uri
            return {'url': url}

        # static
        entries = [
            make_entry(),
            make_entry('/'),
            make_entry('/en/'),
            make_entry('/ru/'),
            make_entry('/account/quick-buy-sell'),
            make_entry('/account/portfolio'),
            make_entry('/account/fees'),
        ]

        for pair in Pair.objects.all():
            entries.append(make_entry(f'/account/trade/{pair.code}'))

        from seo.models import CoinStaticPage
        # todo move from core ??
        coins = list([c.code for c in CoinStaticPage.objects.values_list('currency', flat=True)])
        langs = settings.MODELTRANSLATION_LANGUAGES

        for lang in langs:
            activate(lang)

            for coin in coins:
                entries.append(make_entry(reverse('coin-item', kwargs={'request_ticker': coin})))

        result = render_to_string('sitemap.xml', context={'entries': entries})
        # activate(current_language)
        facade_cache.set(cache_key, result, timeout=3600*24)
    return result
