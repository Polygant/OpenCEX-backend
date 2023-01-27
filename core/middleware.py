import logging.handlers
import re

from django.utils import translation
from django_user_agents.utils import get_user_agent
from ipware import get_client_ip
from user_agents.parsers import UserAgent
from core.models.facade import AccessLog

# if not os.path.exists('logs'):
#     os.mkdir('logs')
#
# access_log = logging.getLogger('access_log')
# access_log.setLevel(logging.INFO)
# formatter = logging.Formatter(
#     '%(remote_addr)s [%(asctime)s] %(username)s '
#     '"%(request_method)s %(path_info)s" %(status)s "%(http_user_agent)s"'
# )
# handler = logging.handlers.RotatingFileHandler('logs/access.log', maxBytes=1024000000, backupCount=30)
# handler.setFormatter(formatter)
# access_log.addHandler(handler)

BOT_RE = "^bot[0-9]+@bot.com$"
log = logging.getLogger(__name__)


class AccessLogsMiddleware:
    # TODO? https://stackoverflow.com/questions/1275486/django-how-can-i-see-a-list-of-urlpatterns/23874019
    """Writes django's access logs to table core.AccessLog"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in ['GET', 'PUT'] and request.path_info.startswith('/api/'):
            return response

        for p in ['/favicon.ico', '/api/v1/stats/', '/api/v1/language/']:
            if request.path_info.startswith(p):
                return response

        if '/jsi18n/' in request.path_info:
            return response

        # skip bots requests
        username = 'anonymous' if request.user.is_anonymous else request.user.username or request.user.email
        if re.match(BOT_RE, username):
            return response

        remote_addr = get_client_ip(request)[0]

        if request.META.get('HTTP_CF_CONNECTING_IP'):
            remote_addr = request.META.get('HTTP_CF_CONNECTING_IP')

        user_agent: UserAgent = get_user_agent(request)
        referer = request.META.get('HTTP_REFERER', '-')

        query_string = '&'.join(
            [f'{k}={v}' for k, v in request.GET.items() if 'cf_chl_jschl_tk' in k]
        )
        query_string = '?' + query_string if query_string else ''

        try:
            AccessLog.objects.create(
                ip=remote_addr,
                username=username,
                method=request.method,
                uri=request.path_info + query_string,
                status=str(response.status_code),
                referer=referer,
                user_agent=user_agent.ua_string or '-',
            )
        except Exception as e:
            log.error(str(e))

        # data = {
        #     'remote_addr': remote_addr,
        #     'username': username,
        #     'request_method': request.method,
        #     'path_info': request.path_info + request.META.get('QUERY_STRING', ''),
        #     'http_user_agent': user_agent.ua_string or '-',
        #     'status': str(response.status_code),
        # }
        # access_log.info('', extra=data)
        return response


def force_default_language_middleware(get_response):
    """
        Ignore Accept-Language HTTP headers

        This will force the I18N machinery to always choose settings.LANGUAGE_CODE
        as the default initial language, unless another one is set via sessions or cookies

        Should be installed *before* any middleware that checks request.META['HTTP_ACCEPT_LANGUAGE'],
        namely django.middleware.locale.LocaleMiddleware
        """
    # One-time configuration and initialization.

    def middleware(request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        response = get_response(request)

        if 'HTTP_ACCEPT_LANGUAGE' in request.META and request.COOKIES.get('lang'):
            del request.META['HTTP_ACCEPT_LANGUAGE']
        else:
            lang = 'ru' if request.META.get('HTTP_ACCEPT_LANGUAGE', '').lower().startswith('ru-ru') else 'en'
            response.set_cookie('lang', lang)

        return response

    return middleware


class SetupTranslationsLang:
    """
    Setup translations for rest framework errors
    """
    API_LANGUAGE_HEADER_NAME = 'HTTP_X_API_LANG'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.META.get(self.API_LANGUAGE_HEADER_NAME)
        if lang is not None:
            translation.activate(lang)

        return self.get_response(request)
