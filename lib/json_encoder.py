import datetime
from datetime import timezone

from jsonfield.encoder import JSONEncoder as BaseJSONEncoder
from rest_framework.renderers import JSONRenderer as BaseJSONRenderer


# todo: remove
class JsonEncoder(BaseJSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__json__'):
            return obj.__json__()
        if isinstance(obj, datetime.datetime):
            timestamp = obj.replace(tzinfo=timezone.utc).timestamp() * 1000
            return timestamp
        return BaseJSONEncoder.default(self, obj)


class JSONRenderer(BaseJSONRenderer):
    encoder_class = JsonEncoder
