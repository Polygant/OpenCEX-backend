import logging
import math
import time

from django.db import transaction
from django.db.transaction import atomic
from django_chunked_iterator import batch_iterator

logger = logging.getLogger(__name__)


def chunks(l, n):
    """ iterator without len(list) usage"""
    buf = []
    for i in l:
        buf.append(i)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf


def list_chunks(length, n):
    return [i for i in chunks(length, n)]


class BatchProcessor:
    ITERATE_BATCH_SIZE = 100_000
    COMMIT_ON_BATCH = False

    def start(self):
        with atomic():
            qs = self.make_qs()
            self.iterate(qs)

    def make_batch_iter_qs(self, qs, size):
        return batch_iterator(qs, batch_size=size)

    def make_batch_iter(self, qs, size):
        return chunks(qs, size)

    def iterate(self, qs):
        num_batches = math.ceil(qs.count() / self.ITERATE_BATCH_SIZE)
        cnt = 0
        st = time.time()
        for items in self.make_batch_iter(qs, self.ITERATE_BATCH_SIZE):
            results = []
            for i in items:
                item = self.make_item(i)
                if item is not None:
                    results.append(item)

            self.process_batch(results)
            if self.COMMIT_ON_BATCH:
                transaction.commit()
            cnt += 1

            logger.info(f'{cnt}/{num_batches} {time.time()-st}')
            st = time.time()

    def make_item(self, obj):
        raise NotImplementedError

    def process_batch(self, items):
        raise NotImplementedError

    def make_qs(self):
        raise NotImplementedError
