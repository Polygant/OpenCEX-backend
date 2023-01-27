import logging
import time

from lib.cache import PrefixedRedisCache
from lib.utils import generate_random_string
from lib.utils import threaded


class AlreadyLocked(Exception):
    pass


class NotLocked(Exception):
    pass


class NotOwnLock(Exception):
    pass


logger = logging.getLogger(__name__)


class AutoLock(object):
    """ lock while process is working by auto update timeout on redis key """
    PREFIX = None
    LOCK_PERIOD = 5
    EXCEPTION_NOT_LOCKED = False

    def __init__(self, name):
        self.name = name
        self.value = generate_random_string(10)
        self.cache = PrefixedRedisCache.get_cache(prefix=self.PREFIX or 'auto-lock-')
        self.work = None

    def acquire(self):
        if self.work:
            raise AlreadyLocked()
        r = self.cache.set(self.name, self.value, timeout=self.LOCK_PERIOD, nx=True)
        if not r:
            raise AlreadyLocked()
        self.work = generate_random_string(5)
        self.updater()

    def release(self, *args, **kwargs):
        if not self.is_locked():
            if self.EXCEPTION_NOT_LOCKED:
                raise NotLocked()
            else:
                logger.debug('Not locked!')

        if not self.work:
            raise NotOwnLock()

        self.work = None
        self.cache.delete(self.name)

    def is_locked(self):
        return bool(self.cache.get(self.name, default=None))

    @threaded
    def updater(self):
        work = self.work
        while self.work == work:
            self._prolong_lock()
            time.sleep(self.LOCK_PERIOD * 0.9)

    def _prolong_lock(self):
        self.cache.expire(self.name, timeout=self.LOCK_PERIOD)


class MultiLock(object):
    LOCK_CLASS = AutoLock

    def __init__(self, names):
        self.names = list(names)
        self.locks = {}

    def acquire(self):
        try:
            for name in self.names:
                lock = self.LOCK_CLASS(name)
                lock.acquire()
                self.locks[name] = lock
        except AlreadyLocked:
            self.release()
            raise

    def release(self):
        for i in self.locks.values():
            i.release()
        self.locks = {}
