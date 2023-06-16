from dateutil.relativedelta import relativedelta
from django.db.models import F
from django.db.models.aggregates import Avg
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
from django.db.models.aggregates import Sum
from django.db.models.expressions import Case
from django.db.models.expressions import ValueRange
from django.db.models.expressions import When
from django.db.models.expressions import Window
from django.db.models.fields import IntegerField
from django.db.models.functions.window import FirstValue
from django.db.models.functions.window import LastValue
from django.utils.timezone import now

from lib.batch import BatchProcessor
from core.consts.orders import BUY
from core.consts.orders import SELL
from core.models.orders import ExecutionResult
from core.models.inouts.pair import Pair
from core.models.stats import TradesAggregatedStats
from core.utils.stats.periodic_data_aggregator import PeriodicDataAggregator
from lib.fields import MoneyField


class TradesAggregator(BatchProcessor):
    """ Creates TradesAggregatedStats from execution results """

    PERIODS = {
        'minute': relativedelta(minutes=1),
        'hour': relativedelta(hours=1),
        'day': relativedelta(days=1),

    }

    def __init__(self, pair, period):
        self.period = period
        self.pair = Pair.get(pair)

    @classmethod
    def aggregates(cls):
        frame = ValueRange()
        parition = (F('ts'), F('pair'))
        return dict(
            close_price=Window(
                expression=LastValue('price'),
                order_by=[F('created')],
                frame=frame,
                partition_by=parition,
            ),
            open_price=Window(
                expression=FirstValue('price'),
                order_by=[F('created')],
                frame=frame,
                partition_by=parition,
            ),
            min_price=Window(
                expression=Min('price'),
                partition_by=parition,
            ),
            max_price=Window(
                expression=Max('price'),
                partition_by=parition,
            ),
            avg_price=Window(
                expression=Avg('price'),
                partition_by=parition,
            ),
            amount=Window(
                expression=Sum(F('quantity') / 2.0, output_field=MoneyField()),
                partition_by=parition,
            ),
            volume=Window(
                expression=Sum(F('quantity') * F('price') / 2.0, output_field=MoneyField()),
                partition_by=parition,
            ),
            num_trades=Window(
                expression=Sum(
                    Case(
                        When(
                            order__operation=BUY,
                            then=1
                        ),
                        output_field=IntegerField()
                    )
                ),
                partition_by=parition,
            ),
            fee_base=Window(
                expression=Sum(
                    Case(
                        When(
                            order__operation=BUY,
                            then=F('fee_amount')
                        )
                        , output_field=MoneyField()
                    )
                ),
                partition_by=parition,
            ),
            fee_quoted=Window(
                expression=Sum(
                    Case(
                        When(
                            order__operation=SELL,
                            then=F('fee_amount')
                        )
                        , output_field=MoneyField()
                    )
                ),
                partition_by=parition,
            ),
        )

    @classmethod
    def filter_to_last_period(cls, period):
        trunc = {
            'microsecond': 0,
            'second': 0
        }
        if period == 'hour':
            trunc['minute'] = 0

        if period == 'day':
            trunc['minute'] = 0
            trunc['hour'] = 0
        return {'created__lt': now().replace(**trunc)}

    @classmethod
    def filter_from_last_record(cls, pair, period):
        obj = TradesAggregatedStats.objects.filter(
            pair=pair,
            period=TradesAggregatedStats.PERIODS[period]
        ).order_by('-ts').first()

        if not obj:
            return {}

        return {'created__gte': obj.ts + cls.PERIODS[period]}

    def make_item(self, obj):
        for k, v in obj.items():
            if v is None:
                obj[k] = 0
        item = TradesAggregatedStats(
            period=TradesAggregatedStats.PERIODS[self.period],
            **obj)

        return item

    def process_batch(self, items):
        TradesAggregatedStats.objects.bulk_create(items)

    def make_qs(self):
        filters = self.filter_from_last_record(self.pair, self.period)
        filters.update(self.filter_to_last_period(self.period))
        qs = ExecutionResult.objects.filter(cancelled=False, pair=self.pair)

        pda = PeriodicDataAggregator(
            qs=qs,
            period=self.period,
            aggregates=self.aggregates(),
            group_by=['pair_id']
        )

        return pda.aggregate(filters=filters)
