import decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils.timezone import now
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models.orders import ExecutionResult
from core.models.stats import TradesAggregatedStats
from core.models.inouts.pair import Pair
from core.models.inouts.pair import PairSerialField
from core.serializers.stats import StatsSerializer
from core.utils.stats.chart import ChartTool
from core.utils.stats.chart import TimelineGenerator
from core.utils.stats.periodic_data_aggregator import PeriodicDataAggregator
from core.utils.stats.trades_aggregate import TradesAggregator
from lib.helpers import dt_from_js


class PairTradeChartData:
    """ uses Execution results only """
    FIELDS = [
        'ts',
        'max_price',
        'min_price',
        'amount',
        'open_price',
        'close_price'
    ]

    def __init__(self, start, stop, period, pair):
        self.original_start = start
        self.original_stop = stop
        self.start = TimelineGenerator.get_start_for_period(start, period)
        self.stop = TimelineGenerator.get_start_for_period(stop, period)
        self.period = period
        self.pair = Pair.get(pair)
        self.chart_tool = self.make_charttool()

    def make_charttool(self):
        return ChartTool(self.start, self.stop, self.period)

    def get_last_price(self, before_ts):
        match = ExecutionResult.objects.filter(
            cancelled=False,
            pair=self.pair,
            created__lte=before_ts
        ).order_by('-created').first()
        return match.price if match else 0

    def get(self):
        data = self.chart_data_map()

        records = self.chart_tool.populate_with_data(
            data,
            empty_record_maker=self.empty_record,
        )

        return list(map(self.format_item, records))

    def format_item(self, item):
        return [item[f] for f in self.FIELDS]

    def empty_record(self, ts, result_list, **kwargs):
        data = {i: decimal.Decimal(0) for i in self.FIELDS}

        if result_list:
            prev_record = result_list[-1]
            previous_price = prev_record['close_price']
        else:
            previous_price = self.get_last_price(self.start)

        data['open_price'] = previous_price
        data['close_price'] = previous_price
        data['min_price'] = previous_price
        data['max_price'] = previous_price

        data['ts'] = ts
        return data

    def base_qs(self):
        """ data source for aggregation """
        qs = ExecutionResult.objects.filter(
            cancelled=False,
            pair=self.pair,
            created__gte=self.start,
            created__lte=self.stop
        )
        return qs

    def chart_data_map(self):
        qs = self.queryset()
        return self.chart_tool.map_qs(qs, 'ts')

    def queryset(self):
        qs = self.base_qs()
        return self.do_aggregate(qs)

    def do_aggregate(self, qs):
        pda = PeriodicDataAggregator(
            qs=qs,
            period=self.period,
            aggregates=TradesAggregator.aggregates(),
            group_by=['pair_id'],
        )
        return pda.aggregate()


class PairTradeChartDataWithPreAggregattion(PairTradeChartData):
    """ uses TradesAggregatedStats as main data source and execution results only for fresh data """

    def prev_periods(self, period):
        if period == 'minute':
            return 5
        elif period == 'hour':
            return 2
        elif period == 'day':
            return 1
        return 2

    def base_qs(self):
        """ last X periods from now for realtime chart """

        relative = {f'{self.period}s': self.prev_periods(self.period)}
        start = now() - relativedelta(**relative)
        start = TimelineGenerator.get_start_for_period(start, self.period)
        stop = TimelineGenerator.get_stop_for_period(now(), self.period)

        qs = ExecutionResult.objects.filter(
            cancelled=False,
            pair=self.pair,
            created__gte=start,
            created__lte=stop
        )
        return qs

    def get_cached_qs(self, period=None, start=None, stop=None):
        if not period:
            period = self.period
        if not start:
            start = self.start
        if not stop:
            stop = self.stop

        period = TradesAggregatedStats.PERIODS[period]
        qs = TradesAggregatedStats.objects.filter(
            pair=self.pair,
            period=period,
            ts__gte=start,
            ts__lte=stop
        ).values(
            'ts',
            'pair',
            *TradesAggregatedStats.STATS_FIELDS,
        )
        return qs

    def chart_data_map(self):
        week_ago = now() - relativedelta(days=settings.STATS_CLEANUP_MINUTE_INTERVAL_DAYS_AGO)
        before_data_qs = None

        if self.period == 'minute' and self.start < week_ago:
            before_data_qs = self.get_cached_qs('hour', stop=week_ago)
            cached_qs = self.get_cached_qs(start=week_ago)
        else:
            cached_qs = self.get_cached_qs()

        qs = self.queryset()  # fresh only data
        data = self.chart_tool.map_qs(cached_qs, 'ts')
        data.update(self.chart_tool.map_qs(qs, 'ts'))

        if before_data_qs:
            data.update(self.chart_tool.map_qs(before_data_qs, 'ts'))
        return data


class StatsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ['post']
    CHART_DATA_SOURCE = PairTradeChartDataWithPreAggregattion

    @extend_schema(
        request=StatsSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "records": [
                        [
                            1000000000000.0,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                        ],
                    ],
                    "start": 1000000000000,
                    "stop": 1000000000000,
                    "frame": "minute",
                    "last_record_dt": "2000-01-01 00:00:00+00:00"
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def post(self, request, **kwargs):
        serializer = StatsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spec = serializer.data

        start = dt_from_js(spec['start_ts'])
        stop = dt_from_js(spec['stop_ts'])

        if stop > now():
            stop = now()

        st = self.CHART_DATA_SOURCE(
            start=start,
            stop=stop,
            period=spec['frame'],
            pair=spec['pair']
        )

        records = st.get()

        response = {
            'records': records,
            'start': spec['start_ts'],
            'stop': spec['stop_ts'],
            'frame': spec['frame'],
            'last_record_dt': None if not records else str((records[-1][0]))
        }
        return Response(response)


class PairSerializer(serializers.Serializer):
    pair = PairSerialField()
