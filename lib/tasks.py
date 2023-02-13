import enum
import logging
import pickle

from celery.utils.serialization import b64encode, b64decode

from .exceptions import BaseError


log = logging.getLogger(__name__)


class WrappedTaskResultStatus(enum.IntEnum):
    ERROR = 0
    OK = 1


class WrappedTaskManager:

    @classmethod
    def wrap_fn(cls, fn, *args, **kwargs):
        try:
            return WrappedTaskManager.pack_result(fn(*args, **kwargs))
        except Exception as exc:
            return WrappedTaskManager.pack_exception(exc)

    @classmethod
    def pack_result(cls, data=None) -> dict:
        return {
            'status': WrappedTaskResultStatus.OK.value,
            'data': data,
        }

    @classmethod
    def pack_exception(cls, exc) -> dict:
        exc_type = type(exc)

        if isinstance(exc, BaseError):
            args, kwargs = getattr(exc, '_args'), getattr(exc, '_kwargs')

        # reraise if unknown
        else:
            raise exc

        return {
            'status': WrappedTaskResultStatus.ERROR.value,
            'type': cls._pack_object(exc_type),
            'args': cls._pack_object(args),
            'kwargs': cls._pack_object(kwargs),
        }

    @classmethod
    def unpack_result_or_raise(cls, result: dict):
        print(result)
        if result['status'] == WrappedTaskResultStatus.OK:
            return result['data']

        else:
            exc_type = cls._unpack_object(result['type'])
            args = cls._unpack_object(result['args'])
            kwargs = cls._unpack_object(result['kwargs'])

            raise exc_type(*args, **kwargs)

    @staticmethod
    def _pack_object(obj):
        return b64encode(pickle.dumps(obj))

    @staticmethod
    def _unpack_object(packed_obj):
        return pickle.loads(b64decode(packed_obj))
