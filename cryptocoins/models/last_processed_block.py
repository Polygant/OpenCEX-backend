from django.db import models

from core.currency import CurrencyModelField
from exchange.models import BaseModel


class LastProcessedBlock(BaseModel):
    currency = CurrencyModelField(unique=True, db_index=True)
    block_id = models.BigIntegerField(default=0)

    def __str__(self):
        return f'{self.currency}: {self.block_id}'
