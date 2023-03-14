import datetime
import random
import re
import string
import traceback
from contextlib import contextmanager
from functools import partial
from functools import wraps
from random import SystemRandom
from threading import Thread

from time import monotonic
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

LOCK_EXPIRE = 60 * 10  # Lock expires in 10 minutes
CAMEL_TO_SNAKE_RE = re.compile('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))')

try:
    # Django 3.1 and above
    from django.shortcuts import render_to_response as render
except ImportError:
    from django.shortcuts import render


class RunThread(Thread):
    def __init__(self, target_function):
        self.target_function = target_function
        super(RunThread, self).__init__()

    def run(self):
        return self.target_function(self)


def threaded(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""
    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper


def threaded_daemon(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""
    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread
    return wrapper


def get_domain():
    from django.contrib.sites.models import Site
    return Site.objects.get_current().domain


def get_api_domain():
    return 'api.{}'.format(get_domain())


def notify_on_error(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as exc:
            subj = 'On {} Exception at {}'.format(settings.INSTANCE_NAME, f)
            msg = 'instance name: {}\n'.format(settings.INSTANCE_NAME)
            msg += '{}\n'.format(str(exc))
            msg += '\n'.join((traceback.format_tb(exc.__traceback__)))
            send_mail(subj, msg, settings.DEFAULT_FROM_EMAIL, settings.INTERGRATOR_REPORTS_EMAILS)
            raise
    return wrap


@contextmanager
def memcache_lock(lock_id, oid=None, expire=None):
    oid = oid or lock_id
    expire = expire or LOCK_EXPIRE
    timeout_at = monotonic() + expire - 3
    # cache.add fails if the key already exists
    status = cache.add(lock_id, oid, expire)
    try:
        yield status
    finally:
        # memcache delete is very slow, but we have to use it to take
        # advantage of using add() for atomic locking
        if monotonic() < timeout_at:
            # don't release the lock if we exceeded the timeout
            # to lessen the chance of releasing an expired lock
            # owned by someone else.
            cache.delete(lock_id)


def generate_random_string(length: int, symbols=None):
    symbols = symbols or string.ascii_letters + string.digits

    return ''.join(SystemRandom().choice(symbols) for _ in range(length))

hmac_random_string = partial(generate_random_string, length=32)


def generate_random_int(min_limit: int, max_limit: int):
    return random.randint(min_limit, max_limit)


random_integer = partial(generate_random_int, min_limit=1, max_limit=40)


from datetime import timezone


def dt2ts(dt):
    return dt.replace(tzinfo=timezone.utc).timestamp()


def ts2dt(ts, tz=timezone.utc):
    return datetime.datetime.fromtimestamp(ts, tz=timezone.utc)


def camel_to_snake_string(value: str) -> str:
    return CAMEL_TO_SNAKE_RE.sub(r'_\1', value).lower()


@contextmanager
def suppress_autotime(model, fields):
    _original_values = {}
    for field in model._meta.local_fields:
        if field.name in fields:
            _original_values[field.name] = {
                'auto_now': field.auto_now,
                'auto_now_add': field.auto_now_add,
            }
            field.auto_now = False
            field.auto_now_add = False
    try:
        yield
    finally:
        for field in model._meta.local_fields:
            if field.name in fields:
                field.auto_now = _original_values[field.name]['auto_now']
                field.auto_now_add = _original_values[field.name]['auto_now_add']


def exception_handler(exc, context):
    """
    Returns the response that should be used for any given exception.

    By default we handle the REST framework `APIException`, and also
    Django's built-in `Http404` and `PermissionDenied` exceptions.

    Any unhandled exceptions may return `None`, which will cause a 500 error
    to be raised.
    """
    from rest_framework.views import set_rollback

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, exceptions.APIException):
        headers = {}
        if getattr(exc, 'auth_header', None):
            headers['WWW-Authenticate'] = exc.auth_header
        if getattr(exc, 'wait', None):
            headers['Retry-After'] = '%d' % exc.wait

        if isinstance(exc.detail, (list, dict)):
            data = exc.get_full_details()
        else:
            data = {
                'detail': exc.detail,
                'message': exc.detail,
                'type': exc.get_codes()
            }

            if getattr(exc, 'wait', None):
                data['wait'] = '%d' % exc.wait

        set_rollback()
        return Response(data, status=exc.status_code, headers=headers)

    return None