import datetime
import decimal
import logging
from _decimal import Decimal
from collections import Counter
from itertools import chain

from django.conf import settings
from django.utils import timezone
from django.utils.translation import get_language
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.generics import GenericAPIView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.consts.orders import EXTERNAL
from core.consts.orders import BUY
from core.consts.orders import ORDER_CLOSED
from core.consts.orders import ORDER_OPENED
from core.exceptions.orders import OrderNotFoundError, OrderNotOpenedError, OrderMinQuantityError
from core.filters.orders import OrdersFilter, ExchangeFilter
from core.utils.stats.daily import get_filtered_pairs_24h_stats, get_pair_last_price
from core.orderbook.helpers import get_stack_by_pair
from core.models import PairSettings
from core.models.orders import Exchange
from core.models.orders import ExecutionResult
from core.models.orders import Order
from core.otcupdater import OtcOrdersUpdater
from core.pairs import PAIRS
from core.pairs import Pair
from core.permissions import BotsOnly
from core.serializers.orders import ExchangeRequestSerializer, StopLimitOrderSerializer, AllOrdersSimpleSerializer
from core.serializers.orders import ExchangeResultSerialzier
from core.serializers.orders import ExecutionResultSerializer
from core.serializers.orders import LimitOnlyOrderSerializer
from core.serializers.orders import OrderSerializer
from core.serializers.orders import UpdateOrderSerializer
from core.tasks import orders
from lib.countless_pagination import CountLessPaginator
from lib.exceptions import BaseError
from lib.filterbackend import FilterBackend
from lib.helpers import calc_absolute_percent_difference
from lib.helpers import to_decimal
from lib.orders_helper import prepare_market_data, market_cost_and_price, get_cost_and_price
from lib.permissions import IsPUTOrIsAuthenticated
from lib.tasks import WrappedTaskManager
from lib.views import ExceptionHandlerMixin

log = logging.getLogger(__name__)


class OrdersView(ExceptionHandlerMixin,
                 mixins.CreateModelMixin,
                 mixins.DestroyModelMixin,
                 viewsets.ReadOnlyModelViewSet):
    # permission_classes = (AllowAny,)
    serializer_class = LimitOnlyOrderSerializer
    queryset = Order.objects.all()

    filter_backends = (FilterBackend,)
    filter_class = OrdersFilter

    def get_queryset(self):
        qs = super(OrdersView, self).get_queryset().order_by('-id')
        if self.request.user.is_anonymous:
            return qs.filter(user_id=0)
        return qs.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.delete()

    def perform_create(self, serializer):
        serializer.save()


class LastExecutedOrdersView(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.filter(executed=True, state=ORDER_CLOSED).order_by('-updated')

    filter_backends = (FilterBackend,)
    filterset_fields = ('pair', 'type', 'operation')


class LastTradesView(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    pagination_class = CountLessPaginator
    serializer_class = ExecutionResultSerializer
    queryset = ExecutionResult.qs_last_executed(
        ExecutionResult.objects.all().select_related('order')
    )

    filter_backends = (FilterBackend,)
    filterset_fields = ('pair',)


def stack_iter(stack):
    for i in stack:
        yield (i['price'], i['quantity'])


class StopLimitView(ExceptionHandlerMixin, GenericAPIView):
    SERIALIZER = StopLimitOrderSerializer
    TASK = orders.stop_limit_order_wrapped

    def data(self, request):
        data = request.data
        return prepare_market_data(request.user, data, self.SERIALIZER)

    @extend_schema(
        request=StopLimitOrderSerializer,
        responses=OrderSerializer
    )
    def post(self, request):

        serializer_item = self.SERIALIZER(data=request.data, context={"request": request})
        serializer_item.is_valid(raise_exception=True)
        data = serializer_item.data
        data['pair_name'] = Pair.get(data['pair']).code
        data['pair_id'] = Pair.get(data['pair']).id
        data['user_id'] = request.user.id

        try:
            wrapped_result = self.TASK.apply_async([data], queue='orders.{}'.format(data['pair_name'].upper()))
            result = WrappedTaskManager.unpack_result_or_raise(wrapped_result.get(timeout=10))
        except Exception as e:
            if isinstance(e, (BaseError, APIException)):
                raise e
            raise APIException(detail=str(e), code='server_error')
        return Response(result)


class MarketView(ExceptionHandlerMixin, GenericAPIView):
    SERIALIZER = OrderSerializer
    TASK = orders.market_order_wrapped

    def data(self, request):
        data = request.data
        return prepare_market_data(request.user, data, self.SERIALIZER)

    @extend_schema(
        request=OrderSerializer,
        responses=OrderSerializer
    )
    def post(self, request):

        cost, price = self.get_cost_and_price(request)

        if cost == 0 or price == 0:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        data = self.data(request)

        try:
            wrapped_result = self.TASK.apply_async([data], queue='orders.{}'.format(data['pair_name'].upper()))
            result = WrappedTaskManager.unpack_result_or_raise(wrapped_result.get(timeout=10))
        except Exception as e:
            if isinstance(e, (BaseError, APIException)):
                raise e
            raise APIException(detail=str(e), code='server_error')
        return Response(result)

    @extend_schema(
        request=OrderSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'price': 0,
                    'cost': 0,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def put(self, request):
        # just find price
        data = self.data(request)
        cost, price = self.market_cost_price(data['pair_name'], data['operation'], data['quantity']) or 0
        return Response({'price': price, 'cost': cost})

    @staticmethod
    def market_cost_price(pair_name, operation, quantity):
        return market_cost_and_price(pair_name, operation, quantity)

    def get_cost_and_price(self, request):
        return get_cost_and_price(request.user, request.data, self.SERIALIZER)


class ExchangeView(ListAPIView, MarketView):
    permission_classes = (IsPUTOrIsAuthenticated,)
    SERIALIZER = ExchangeRequestSerializer
    TASK = orders.exchange_order_wrapped

    serializer_class = ExchangeResultSerialzier
    queryset = Exchange.objects.all().select_related('order').order_by('-id')

    filter_backends = (FilterBackend,)
    filterset_class = ExchangeFilter
    # filterset_fields = ('operation', 'base_currency', 'quote_currency', 'order__state')

    def get_queryset(self):
        qs = super(ExchangeView, self).get_queryset()
        return qs.filter(user=self.request.user)

    def put(self, request):
        # just find price
        cost, price = self.get_cost_and_price(request)
        data = self.data(request)
        disable_exchange = False

        if cost == 0 or price == 0:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        last_price = StackView.get_last_price(data['pair_name'])
        if not data['strict_pair']:
            if last_price:
                last_price = 1 / last_price

        if last_price and price:
            percent_diff = calc_absolute_percent_difference(last_price, price)
            disable_exchange = percent_diff > settings.EXCHANGE_LIMIT_PERCENTAGE

        return Response({
            'price': price,
            'cost': cost,
            'disable_exchange': disable_exchange
        })


class PairsListView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ['get']

    @extend_schema(
        request=OrderSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                  "pairs": [
                    {
                      "id": 1,
                      "code": "BTC-USDT",
                      "base": {
                        "id": 1,
                        "code": "BTC",
                        "is_token": False,
                        "blockchain_list": []
                      },
                      "quote": {
                        "id": 4,
                        "code": "USDT",
                        "is_token": True,
                        "blockchain_list": [
                          "ETH",
                          "BNB",
                          "TRX"
                        ]
                      },
                      "stack_precisions": [
                        "100",
                        "10",
                        "1",
                        "0.1",
                        "0.01"
                      ]
                    },
                  ]
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request, currency=None, format=None):
        res = []
        for p in PAIRS:
            if p.code in PairSettings.get_disabled_pairs():
                continue
            pair_data = p.to_dict()
            pair_data['stack_precisions'] = PairSettings.get_stack_precisions_by_pair(p.code)
            res.append(pair_data)
        return Response({'pairs': res})


class StackView(APIView):
    http_method_names = ['get']
    permission_classes = (AllowAny,)

    @classmethod
    def get_stack_by_name(cls, pair):
        return get_stack_by_pair(pair)

    @classmethod
    def stack_limited(cls, pair, sell_limit=None, buy_limit=None):
        data = cls.get_stack_by_name(pair)
        if sell_limit is not None:
            data['sells'] = data.get('sells', [])[:sell_limit]
        if buy_limit is not None:
            data['buys'] = data.get('buys', [])[:buy_limit]
        return data

    @classmethod
    def get_last_price(cls, pair):
        pair = Pair.get(pair)
        return get_pair_last_price(pair)

    @classmethod
    def group(cls, data, precision='0.001', reverse=False):
        cnt = Counter()
        for i in data:
            p = Decimal(i['price']).quantize(Decimal(str(precision)), rounding=decimal.ROUND_DOWN)
            cnt[p] += i['quantity']
        return [{'price': i, 'quantity': cnt[i]} for i in sorted(cnt.keys(), reverse=reverse)]

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "sells_w_avg": 0.0,
                    "buys_w_avg": 0.0,
                    "sells_volume": 0.0,
                    "buys_volume": 0.0,
                    "top_sell": 0.0,
                    "top_buy": 0.0,
                    "rate": 0.0,
                    "sells": [
                        {
                            "id": 0,
                            "price": 0.0,
                            "quantity": 0.0,
                            "user_id": 0,
                            "timestamp": 1000000000.000000,
                            "depth": 0.0
                        },
                    ],
                    "buys": [
                        {
                            "id": 0,
                            "price": 0.0,
                            "quantity": 0.0,
                            "user_id": 0,
                            "timestamp": 1000000000.000000,
                            "depth": 0.0
                        },
                    ],
                    "ts": 1000000000000.0000,
                    "last_proceed": 1000000000000,
                    "last_update": 1000000000000,
                    "down_multiplier": 1,
                    "down_send_time": None,
                    "pair": "BTC-USDT",
                    "last_price": 0.0
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ],
        parameters=[
            OpenApiParameter(required=False, type=int, name='group', )
        ]
    )
    def get(self, request, pair, format=None):
        data = self.get_stack_by_name(pair)
        group = to_decimal(request.GET.get('group', 0))

        if data and request.user.id:
            for i in chain(data['sells'], data['buys']):
                if 'user_id' not in i:
                    continue
                i['owner'] = request.user.id == i['user_id']
                del i['user_id']

        if group > 0:
            data['sells'] = self.group(data['sells'], group)
            data['buys'] = self.group(data['buys'], group)

        if data:
            # TODO: do a cache!
            data['last_price'] = self.get_last_price(pair)
        return Response(data)


class PairsVolumeView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "pairs": [
                        {
                            "volume": 0,
                            "base_volume": 0,
                            "price": 0,
                            "price_24h": 0,
                            "price_24h_value": 0,
                            "pair": "BTC-USDT",
                            "pair_data": {
                                "id": 1,
                                "code": "BTC-USDT",
                                "base": {
                                    "id": 1,
                                    "code": "BTC",
                                    "is_token": False,
                                    "blockchain_list": []
                                },
                                "quote": {
                                    "id": 4,
                                    "code": "USDT",
                                    "is_token": True,
                                    "blockchain_list": [
                                        "ETH"
                                    ]
                                },
                                "stack_precisions": [
                                    "100",
                                    "10",
                                    "1",
                                    "0.1",
                                    "0.01"
                                ]
                            }
                        },
                    ]
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request, format=None):
        data = get_filtered_pairs_24h_stats()
        return Response(data)


class OrderUpdateView(ExceptionHandlerMixin,
                      APIView):
    SERIALIZER = UpdateOrderSerializer

    @extend_schema(
        request=UpdateOrderSerializer,
        responses={
            200: OpenApiResponse(description='No body content.')
        }
    )
    def post(self, request):
        serializer = self.SERIALIZER(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        # Find order
        order = Order.objects.filter(id=data['id'], user=self.request.user).first()
        if order is None:
            raise OrderNotFoundError()

        if order.state != ORDER_OPENED:
            raise OrderNotOpenedError(order=order)

        # if 'special_data' in data and order.type != EXTERNAL:
        #     raise ValidationError('special data only for OTC!')

        # New quantity must be greater than matched quantity
        min_quantity = order.quantity - order.quantity_left
        quantity = data.get('quantity')

        if order.type == EXTERNAL:
            otc_percent = request.data.get('otc_percent', 0)
            otc_limit = request.data.get('otc_limit', 0)

            price = OtcOrdersUpdater.make_price(order.pair, otc_percent)
            if order.operation == BUY:
                data['price'] = min(price, otc_limit)
            else:
                data['price'] = max(price, otc_limit)

        if quantity and quantity <= min_quantity:
            raise OrderMinQuantityError(
                currency=order.pair.base,
                min_quantity=min_quantity,
            )

        wrapped_result = order.update_order(data)
        result = WrappedTaskManager.unpack_result_or_raise(wrapped_result)

        return Response(status=status.HTTP_200_OK, data=result)


class ExchangeEmailView(APIView):
    http_method_names = ['post']

    @extend_schema(exclude=True)
    def post(self, request, format=None):
        lang = get_language()
        data = request.data
        required_params = [
            'base_currency',
            'quote_currency',
            'base_value',
            'quote_value',
        ]
        for param in required_params:
            if param not in data:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        params = {p: data[p] for p in required_params}
        params.update({
            'address': data.get('address'),
            'email': request.user.email

        })

        orders.send_exchange_completed_message.apply_async([params, lang])
        return Response(data)


class AllOrdersView(ListAPIView):
    http_method_names = ['get']
    permission_classes = [BotsOnly]
    serializer_class = AllOrdersSimpleSerializer
    queryset = Order.objects.all().order_by('price',).prefetch_related('user')
    pagination_class = None

    filter_backends = (FilterBackend,)
    filterset_fields = ('pair',)

    def get_queryset(self):
        return super(AllOrdersView, self).get_queryset().filter(
            state=Order.STATE_OPENED,
            in_stack=True,
        )


class LatestCandleView(APIView):
    http_method_names = ['get']
    permission_classes = [BotsOnly]

    @extend_schema(exclude=True)
    def get(self, request):
        pair = request.query_params['pair']
        interval = int(request.query_params.get('interval', 1))  # minutes

        ts_now = int(timezone.now().timestamp())
        interval_sec = interval * 60
        next_ts = (ts_now // interval_sec) * interval_sec + interval_sec
        end_time = datetime.datetime.fromtimestamp(next_ts)
        start_time = end_time - datetime.timedelta(seconds=interval_sec)

        qs = ExecutionResult.objects.filter(
            cancelled=False,
            pair=pair,
            created__gte=start_time,
            created__lte=end_time
        ).order_by('created')

        open_match = qs.first()
        close_match = qs.last()

        open = close = high = low = 0

        if open_match:
            open = open_match.price

        if close_match:
            close = close_match.price

        return Response({
            'time': start_time,
            'open': open,
            'close': close,
            'high': high,
            'low': low,
        })
