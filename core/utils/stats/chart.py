from dateutil.relativedelta import relativedelta

from core.utils.stats.lib import ExchangeQuerySetStats


VALID_PERIODS = [
    'minute',
    'hour',
    'day'
]


class TimelineGenerator:
    PERIODS = VALID_PERIODS

    @classmethod
    def get_start_for_period(cls, dt, period):
        return ExchangeQuerySetStats.bounds_for_interval(
            period,
            dt
        )[0]

    @classmethod
    def get_stop_for_period(cls, dt, period):
        return ExchangeQuerySetStats.bounds_for_interval(
            period,
            dt
        )[1]

    @classmethod
    def generate(cls, start, stop, period):
        dt = cls.get_start_for_period(start, period)
        end = cls.get_start_for_period(stop, period)
        while dt <= end:
            yield dt
            dt = dt + relativedelta(**{
                f'{period}s': 1
            }
                                    )


class ChartTool:
    PERIODS = VALID_PERIODS
    EMPTY_KEY = '_empty_'

    def make_timeline(self):
        return list(TimelineGenerator.generate(self.start, self.stop, self.period))

    def __init__(self, start, stop, period):
        self.start = start
        self.stop = stop
        self.period = period
        self.timeline = self.make_timeline()

    def populate_with_data(self, data, empty_record_maker, result_list=None, field='ts'):
        result_list = result_list if isinstance(result_list, list) else []

        for ts in self.timeline:
            if ts not in data:
                record = empty_record_maker(ts, result_list=result_list)
                record[self.EMPTY_KEY] = True
            else:
                record = data[ts]

            result_list.append(record)
        return result_list

    @classmethod
    def map_qs(cls, qs, field):
        data = {}
        for i in qs:
            data[i[field]] = i

        return data
