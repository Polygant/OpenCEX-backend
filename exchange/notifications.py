from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.utils.timezone import now

from core.orderbook.helpers import get_stack_by_pair
from core.orderbook.helpers import mark_self_stack
from core.models.cryptocoins import UserWallet
from core.models.inouts.balance import Balance
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.models.wallet_history import WalletHistoryItem
from core.pairs import PAIRS
from core.serializers.cryptocoins import UserWalletSerializer
from core.serializers.orders import ExecutionResultSerializer
from core.serializers.orders import OrderSerializer
from core.serializers.wallet_history import WalletHistoryItemSerializer
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from core.views.stats import PairTradeChartDataWithPreAggregattion
from core.views.stats import StatsSerializer
from lib.helpers import dt_from_js
from lib.helpers import find_similar_entry_by_field
from lib.helpers import normalize_data

channel_layer = get_channel_layer()
MSG_TYPE = 'exchange.message'


class BaseNotificator:
    MSG_KIND: str = ''
    PARAMS = []  # required parameters

    def gen_channel(self, **kwargs) -> str:
        ch_name = f'{self.MSG_KIND}_' + '_'.join(str(kwargs.get(k)) for k in self.PARAMS)
        return ch_name

    def prepare_data(self, data, is_notification=False, **kwargs) -> dict:
        data['kind'] = self.MSG_KIND
        data = normalize_data(data)
        if is_notification:
            return {
                'type': MSG_TYPE,
                'data': data
            }
        return data

    def notify(self, data, **kwargs):
        data = self.prepare_data(data, is_notification=True, **kwargs)
        async_to_sync(channel_layer.group_send)(self.gen_channel(**kwargs), data)

    def get_data(self, **kwargs):
        raise NotImplementedError

    def add_data(self, **kwargs):
        raise NotImplementedError


class UserNotificator(BaseNotificator):
    MSG_KIND = 'user_notification'
    PARAMS = ['user_id']


class StackNotificator(BaseNotificator):
    MSG_KIND = 'stack'
    PARAMS = ['pair_name', 'precision']

    def prepare_data(self, data, is_notification=False, **kwargs):
        pair = kwargs['pair_name']
        precision = kwargs.get('precision')
        user_id = kwargs.get('user_id')
        data = mark_self_stack(data, user_id)
        data = normalize_data(data)

        data = {
            'kind': self.MSG_KIND,
            'pair': pair,
            'precision': precision,
            'stack': data,
            'uid': user_id
        }

        if is_notification:
            return {
                'type': MSG_TYPE,
                'data': data,
            }
        return data

    def get_data(self, **kwargs):
        pair = kwargs['pair_name']
        precision = kwargs.get('precision')
        return get_stack_by_pair(pair, precision)


class PairsNotificator(BaseNotificator):
    MSG_KIND = 'pairs'
    PARAMS = []

    def get_data(self, **kwargs):
        from core.models import PairSettings
        res = PairSettings.get_stack_precisions()
        return {'data': res}


class BalanceNotificator(BaseNotificator):
    MSG_KIND = 'balance'
    PARAMS = ['user_id']

    def add_data(self, **kwargs):
        data = self.get_data(**kwargs)
        self.notify(data, **kwargs)

    def get_data(self, **kwargs):
        user_id = kwargs['user_id']
        return {'balance': Balance.for_user(user_id)}


class WalletsNotificator(BaseNotificator):
    MSG_KIND = 'wallets'
    PARAMS = ['user_id']

    def add_data(self, **kwargs):
        data = self.get_data(**kwargs)
        self.notify(data, **kwargs)

    def get_data(self, **kwargs):
        user_id = kwargs['user_id']
        currency = kwargs.get('currency')
        wallets = UserWallet.objects.filter(user_id=user_id, merchant=False, is_old=False)
        if currency:
            wallets = wallets.filter(currency=currency)
        wallet_data = UserWalletSerializer(wallets, many=True).data
        return {'data': wallet_data}


class CoinsStatusNotificator(BaseNotificator):
    MSG_KIND = 'coins_status'
    PARAMS = []

    def get_data(self, **kwargs):
        data = DisabledCoin.get_coins_status()
        return {'data': data}


class FeesAndLimitsNotificator(BaseNotificator):
    MSG_KIND = 'fees_limits'
    PARAMS = []

    def get_data(self, **kwargs):
        data = FeesAndLimits.get_fees_and_limits()
        return {'data': data}


class ChartNotificator(BaseNotificator):
    MSG_KIND = 'chart'
    PARAMS = []

    def get_data(self, **kwargs):
        serializer = StatsSerializer(data=kwargs)
        serializer.is_valid(raise_exception=True)
        spec = serializer.data

        start = dt_from_js(spec['start_ts'])
        stop = dt_from_js(spec['stop_ts'])

        if stop > now():
            stop = now()

        st = PairTradeChartDataWithPreAggregattion(
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
        return response


class PairsVolumeNotificator(BaseNotificator):
    MSG_KIND = 'pairs_volume'
    PARAMS = []

    def add_data(self, **kwargs):
        data = self.get_data(**kwargs)
        self.notify(data, **kwargs)

    def get_data(self, **kwargs):
        return get_filtered_pairs_24h_stats()


# TODO validate pairs?
class BasePaginatedNotificator(BaseNotificator):
    LIMIT: int = 10
    SERIALIZER = None
    PARAMS = []

    def get_cache(self, default=None, **kwargs):
        key = f'wsdata-' + self.gen_channel(**kwargs)
        return cache.get(key) or default

    def set_cache(self, data, **kwargs):
        """
        data = {results: list, total_entries: 0}
        """
        key = f'wsdata-' + self.gen_channel(**kwargs)
        cache.set(key, data, timeout=60)

    def get_paginated_data(self, new_data=None, page=1, limit=0, **kwargs):
        limit = limit or self.LIMIT

        cached_data = self.get_cache(**kwargs)
        delete = kwargs.get('delete')

        if page < 1:
            page = 1
        if limit < 1:
            limit = 1

        if page == 1 and cached_data and len(cached_data['results']) >= limit:
            data = cached_data
            if new_data:
                new_data_dict = self.SERIALIZER(new_data).data
                index, similar_entry = find_similar_entry_by_field('id', new_data.id, data['results'])

                max_id = max(r['id'] for r in cached_data['results'])
                is_new = not new_data_dict['id'] or new_data_dict['id'] > max_id

                if delete:
                    if similar_entry:
                        del data['results'][index]
                    else:
                        return
                    data['total_entries'] -= 1

                else:
                    if similar_entry:
                        similar_entry.update(new_data_dict)
                    elif is_new:
                        del data['results'][-1]
                        data['results'].insert(0, new_data_dict)
                        data['total_entries'] += 1
                    else:
                        # change not visible entry
                        return
                self.set_cache(data, **kwargs)
        else:
            data = self._get_qs_data(page, limit, **kwargs)

        total_pages, mod = divmod(data['total_entries'], limit)
        if mod:
            total_pages += 1
        return {
            'total_pages': total_pages,
            'page': page,
            'results': data['results'],
        }

    def _get_qs_data(self, page=1, limit=10, **kwargs):
        qs = self.get_queryset(**kwargs)
        total_entries = qs.count()
        offset = (page - 1) * limit
        serialized_data = self.SERIALIZER(qs[offset:offset + limit], many=True).data
        data = {'results': serialized_data, 'total_entries': total_entries}
        if page == 1:
            self.set_cache(data, **kwargs)
        return data

    def get_queryset(self, **kwargs):
        raise NotImplementedError

    def parse_new_data(self, **kwargs):
        raise NotImplementedError

    def add_data(self, **kwargs):
        entry, new_kwargs = self.parse_new_data(**kwargs)
        if not entry and not new_kwargs:
            return

        new_kwargs['delete'] = kwargs.get('delete', False)
        data = self.get_paginated_data(entry, **new_kwargs)
        if data:
            self.notify(data, **new_kwargs)


class TradesNotificator(BasePaginatedNotificator):
    MSG_KIND = 'trades'
    LIMIT = 50
    SERIALIZER = ExecutionResultSerializer
    PARAMS = ['pair_name']

    def parse_new_data(self, **kwargs):
        entry: ExecutionResult = kwargs['entry']
        new_kwargs = {
            'pair_name': entry.pair.code
        }
        return entry, new_kwargs

    def get_queryset(self, **kwargs):
        pair = kwargs['pair_name']
        queryset = ExecutionResult.qs_last_executed(
            ExecutionResult.objects.filter(pair=pair).select_related('order')
        ).order_by('-created')
        return queryset


class OpenedOrdersNotificator(BasePaginatedNotificator):
    MSG_KIND = 'opened_orders'
    LIMIT = 7
    SERIALIZER = OrderSerializer
    PARAMS = ['user_id']

    def parse_new_data(self, **kwargs):
        order: Order = kwargs['entry']
        new_kwargs = {
            'user_id': order.user_id,
        }
        return order, new_kwargs

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        queryset = Order.objects.filter(
            user_id=user_id,
            state=Order.STATE_OPENED
        ).order_by('-created')
        return queryset


class ClosedOrdersNotificator(OpenedOrdersNotificator):
    MSG_KIND = 'closed_orders'
    PARAMS = ['user_id']

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        queryset = Order.objects.filter(
            user_id=user_id,
            state__in=[Order.STATE_CLOSED, Order.STATE_REVERT, Order.STATE_CANCELLED]
        ).order_by('-created')
        return queryset


class OpenedOrdersByPairNotificator(OpenedOrdersNotificator):
    MSG_KIND = 'opened_orders_pair'
    PARAMS = ['user_id', 'pair_name']

    def parse_new_data(self, **kwargs):
        order: Order = kwargs['entry']
        new_kwargs = {
            'user_id': order.user_id,
            'pair_name': order.pair.code
        }
        return order, new_kwargs

    def get_queryset(self, **kwargs):
        qs = super().get_queryset(**kwargs)
        pair = kwargs['pair_name']
        qs = qs.filter(pair=pair)
        return qs


class ClosedOrdersByPairNotificator(ClosedOrdersNotificator):
    MSG_KIND = 'closed_orders_pair'
    PARAMS = ['user_id', 'pair_name']

    def parse_new_data(self, **kwargs):
        order: Order = kwargs['entry']
        new_kwargs = {
            'user_id': order.user_id,
            'pair_name': order.pair.code
        }
        return order, new_kwargs

    def get_queryset(self, **kwargs):
        qs = super().get_queryset(**kwargs)
        pair = kwargs['pair_name']
        qs = qs.filter(pair=pair)
        return qs


class OpenedOrdersEndpoint(BaseNotificator):
    MSG_KIND = 'opened_orders'
    LIMIT = 7
    SERIALIZER = OrderSerializer
    PARAMS = ['user_id', 'date_from', 'date_to', 'page']

    def _parse_params(self, **kwargs):
        params = {'user_id': kwargs['user_id']}

        date_from = kwargs.get('date_from')
        if date_from:
            params['created__gte'] = dt_from_js(date_from)

        date_to = kwargs.get('date_to')
        if date_to:
            params['created__lt'] = dt_from_js(date_to)

        params = self.extra_params(params, **kwargs)
        return params

    def extra_params(self, params, **kwargs):
        params['state'] = Order.STATE_OPENED
        return params

    def get_data(self, **kwargs):
        queryset = self.get_queryset(**kwargs)

        page = int(kwargs.get('page') or 1)
        if page < 1:
            page = 1
        offset = (page - 1) * self.LIMIT

        total_entries = queryset.count()
        total_pages, mod = divmod(total_entries, self.LIMIT)

        if mod:
            total_pages += 1
        data = {
            'total_pages': total_pages,
            'page': page,
            'results': self.SERIALIZER(queryset[offset: offset + self.LIMIT], many=True).data
        }
        return data

    def get_queryset(self, **kwargs):
        params = self._parse_params(**kwargs)
        queryset = Order.objects.filter(**params).order_by('-created')
        return queryset


class ClosedOrdersEndpoint(OpenedOrdersEndpoint):
    MSG_KIND = 'closed_orders'

    def extra_params(self, params, **kwargs):
        params['state__in'] = [Order.STATE_CLOSED, Order.STATE_REVERT, Order.STATE_CANCELLED]
        return params


class OpenedOrdersByPairEndpoint(OpenedOrdersEndpoint):
    MSG_KIND = 'opened_orders_pair'
    PARAMS = ['user_id', 'pair_name', 'date_from', 'date_to', 'page']

    def extra_params(self, params, **kwargs):
        params['pair'] = kwargs['pair_name']
        return params


class ClosedOrdersByPairEndpoint(OpenedOrdersByPairEndpoint):
    MSG_KIND = 'closed_orders_pair'

    def extra_params(self, params, **kwargs):
        params['pair'] = kwargs['pair_name']
        params['state__in'] = [Order.STATE_CLOSED, Order.STATE_REVERT, Order.STATE_CANCELLED]
        return params


class ExecutedOrderNotificator(BaseNotificator):
    MSG_KIND = 'executed_order_notification'
    PARAMS = ['user_id']

    def add_data(self, **kwargs):
        order_data = OrderSerializer(kwargs['entry']).data
        order_data['matched_amount'] = kwargs.get('matched_amount') or 0
        data = {'order': order_data}
        self.notify(data, **kwargs)


class WalletHistoryNotificator(BasePaginatedNotificator):
    MSG_KIND = 'wallet_history'
    LIMIT = 10
    SERIALIZER = WalletHistoryItemSerializer
    PARAMS = ['user_id']

    def parse_new_data(self, **kwargs):
        entry: WalletHistoryItem = kwargs['entry']
        new_kwargs = {
            'user_id': entry.user_id,
        }
        return entry, new_kwargs

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        queryset = WalletHistoryItem.objects.filter(
            user_id=user_id
        ).select_related(
            'transaction',
        )
        return queryset


class WalletHistoryEndpoint(BaseNotificator):
    MSG_KIND = 'wallet_history'
    PARAMS = ['user_id', 'date_from', 'date_to', 'limit']

    def add_data(self, **kwargs):
        pass

    def get_data(self, **kwargs):
        params = {'user_id': kwargs['user_id']}
        date_from = kwargs.get('date_from')
        if date_from:
            params['created__gte'] = dt_from_js(date_from)

        date_to = kwargs.get('date_to')
        if date_to:
            params['created__lt'] = dt_from_js(date_to)

        page = int(kwargs.get('page') or 1)
        if page < 1:
            page = 1
        limit = 10
        offset = (page - 1) * limit

        queryset = WalletHistoryItem.objects.filter(**params).select_related(
            'transaction',
        )
        total_entries = queryset.count()
        total_pages, mod = divmod(total_entries, limit)

        if mod:
            total_pages += 1
        data = {
            'total_pages': total_pages,
            'page': page,
            'results': WalletHistoryItemSerializer(queryset[offset: offset+limit], many=True).data
        }

        return data


class WalletTopupsHistoryNotificator(BasePaginatedNotificator):
    MSG_KIND = 'wallet_topups_history'
    LIMIT = 10
    SERIALIZER = WalletHistoryItemSerializer
    PARAMS = ['user_id']

    def parse_new_data(self, **kwargs):
        entry: WalletHistoryItem = kwargs['entry']
        if entry.operation_type != WalletHistoryItem.OPERATION_TYPE_DEPOSIT:
            return None, None

        new_kwargs = {
            'user_id': entry.user_id,
        }
        return entry, new_kwargs

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        queryset = WalletHistoryItem.objects.filter(
            user_id=user_id,
            operation_type=WalletHistoryItem.OPERATION_TYPE_DEPOSIT,
        ).select_related(
            'transaction',
        )
        return queryset


class WalletWithdrawalsHistoryNotificator(BasePaginatedNotificator):
    MSG_KIND = 'wallet_withdrawals_history'
    LIMIT = 10
    SERIALIZER = WalletHistoryItemSerializer
    PARAMS = ['user_id']

    def parse_new_data(self, **kwargs):
        entry: WalletHistoryItem = kwargs['entry']
        if entry.operation_type != WalletHistoryItem.OPERATION_TYPE_WITHDRAWAL:
            return None, None

        new_kwargs = {
            'user_id': entry.user_id,
        }
        return entry, new_kwargs

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        queryset = WalletHistoryItem.objects.filter(
            user_id=user_id,
            operation_type=WalletHistoryItem.OPERATION_TYPE_WITHDRAWAL,
        ).select_related(
            'transaction',
        )
        return queryset


class WalletHistoryTickerNotificator(BasePaginatedNotificator):
    MSG_KIND = 'wallet_history_ticker'
    LIMIT = 10
    SERIALIZER = WalletHistoryItemSerializer
    PARAMS = ['user_id', 'ticker']

    def parse_new_data(self, **kwargs):
        entry: WalletHistoryItem = kwargs['entry']
        new_kwargs = {
            'user_id': entry.user_id,
            'ticker': entry.currency
        }
        return entry, new_kwargs

    def get_queryset(self, **kwargs):
        user_id = kwargs['user_id']
        currency = kwargs['ticker']
        queryset = WalletHistoryItem.objects.filter(
            user_id=user_id,
            currency=currency,
        ).select_related(
            'transaction',
        )
        return queryset

user_notificator = UserNotificator()
stack_notificator = StackNotificator()
chart_notificator = ChartNotificator()
balance_notificator = BalanceNotificator()
trades_notificator = TradesNotificator()
opened_orders_notificator = OpenedOrdersNotificator()
closed_orders_notificator = ClosedOrdersNotificator()
opened_orders_by_pair_notificator = OpenedOrdersByPairNotificator()
closed_orders_by_pair_notificator = ClosedOrdersByPairNotificator()
executed_order_notificator = ExecutedOrderNotificator()
pairs_volume_notificator = PairsVolumeNotificator()
coins_status_notificator = CoinsStatusNotificator()
fees_limits_notificator = FeesAndLimitsNotificator()
wallets_notificator = WalletsNotificator()
wallet_history_notificator = WalletHistoryNotificator()
wallet_history_endpoint = WalletHistoryEndpoint()
wallet_topups_history_notificator = WalletTopupsHistoryNotificator()
wallet_withdrawals_history_notificator = WalletWithdrawalsHistoryNotificator()
wallet_history_ticker_notificator = WalletHistoryTickerNotificator()
pairs_notificator = PairsNotificator()

opened_orders_endpoint = OpenedOrdersEndpoint()
closed_orders_endpoint = ClosedOrdersEndpoint()
opened_orders_by_pair_endpoint = OpenedOrdersByPairEndpoint()
closed_orders_by_pair_endpoint = ClosedOrdersByPairEndpoint()
