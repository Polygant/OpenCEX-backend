from dateutil.relativedelta import relativedelta
from django.db.models.fields import DateTimeField
from django.db.models.functions.datetime import Trunc
from django.db.models.query import QuerySet


class PeriodicDataAggregator:
    """ generic data aggregator for periods """
    PERIODS = {
        'minute': relativedelta(minutes=1),
        'hour': relativedelta(hours=1),
        'day': relativedelta(days=1),

    }

    def __init__(self, qs: QuerySet, period: str, field='created', ts_field='ts', aggregates=None, group_by=None):
        self.qs = qs
        self.period = period
        self.field = field
        self._aggregates = aggregates or {}
        self.ts_field = ts_field
        self.group_by = group_by or []
        self.key = [self.ts_field] + self.group_by
        self.values = self.key + list(self._aggregates.keys())

    @classmethod
    def trunc_period(cls, qs: QuerySet, period: str, field='created', ts_field='ts') -> QuerySet:
        return qs.annotate(**{
            ts_field: Trunc(
                field,
                period,
                output_field=DateTimeField()
            )
        }
        )

    def aggregate(self, filters=None) -> QuerySet:
        qs = self.trunc_period(
            self.qs,
            self.period,
            self.field,
            self.ts_field
        )

        if filters:
            qs = qs.filter(**filters)

        qs = qs.annotate(**self._aggregates)
        qs = qs.distinct(*self.key)
        qs = qs.values(*self.values)
        return qs
