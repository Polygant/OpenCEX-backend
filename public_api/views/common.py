"""Public API views"""

import datetime
import logging
import os
import time

import markdown
from django.conf import settings
from django.db.models import F
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
from django.shortcuts import render
from django.utils.timezone import now
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.utils import extend_schema_view
# from django.core import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.hmac_auth import HMACAuthentication
from core.consts.inouts import DISABLE_STACK
from core.models import PairSettings
from core.models.facade import CoinInfo
from core.models.inouts.balance import Balance
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.orders import ExecutionResult
from core.models.inouts.pair import Pair
from core.serializers.orders import LimitOnlyOrderSerializer, UpdateOrderSerializer
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from core.views.orders import StackView, OrdersView, OrderUpdateView
from lib.helpers import to_decimal
from public_api.mixins import ThrottlingViewMixin, NoAuthMixin
from public_api.serializers.common import ExecutionResultSerializer
from public_api.serializers.common import PairLimitValidationSerializer
from public_api.utils import is_pair_disabled

log = logging.getLogger(__name__)


class AssetsView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(
        summary='Assets',
        examples=[
            OpenApiExample(
                'Response Example',
                value={
                    "BTC": {
                        "name": "Bitcoin"
                    },
                    "ETH": {
                        "name": "Ethereum"
                    },
                    "USDT": {
                        "name": "Tether"
                    },
                }
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        """Returns assets map"""
        response = {}
        coins_info = CoinInfo.get_coins_info()
        for symbol, coin in coins_info.items():
            if DisabledCoin.is_coin_disabled(symbol):
                continue
            response[symbol] = {
                'name': coin.get('name', ''),
            }
        return Response(response)


class InfoView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(summary='Exchange info')
    def get(self, request):
        """Returns overall exchange info"""
        r = settings.EXCHANGE_INFO
        return Response(r)


class TickerView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(
        summary='Tickers',
        examples=[
            OpenApiExample(
                'Response Example',
                value={
                    "ETH_BTC": {
                        "last_price": 0.02046117,
                        "base_volume": 64.73692076,
                        "quote_volume": 1.353921854,
                        "is_frozen": 0
                    },
                    "ETH_USD": {
                        "last_price": 198.82570815,
                        "base_volume": 266.91056844,
                        "quote_volume": 54669.13833,
                        "is_frozen": 0
                    },
                }
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        """Returns stats of markets"""
        pairs_data = get_filtered_pairs_24h_stats(DISABLE_STACK)
        pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
        data = {}

        for pair in Pair.objects.all():
            if is_pair_disabled(pair, DISABLE_STACK):
                continue

            result = {
                'last_price': 0.0,
                'base_volume': 0.0,
                'quote_volume': 0.0,
                'is_frozen': 0
            }
            pair_data = pairs_data.get(pair.code, {})

            result['last_price'] = pair_data.get('price') or 0
            result['quote_volume'] = pair_data.get('volume') or 0
            result['base_volume'] = pair_data.get('base_volume') or 0

            key = f'{pair.base.code}_{pair.quote.code}'
            data[key] = result

        return Response(data, status=status.HTTP_200_OK)


class SummaryView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(
        summary='Summary',
        examples=[
            OpenApiExample(
                'Response Example',
                value={
                    "data": {
                        "BTC_USD": {
                            "last_price": 9503.364483,
                            "high_24h": 9519.215928,
                            "low_24h": 9475.8597,
                            "base_volume": 0.20381013,
                            "quote_volume": 1934.88922435,
                            "lowest_ask": 9503.364483,
                            "highest_bid": 9475.8597,
                            "percent_change": 0.0345,
                            "is_frozen": 0
                        },
                    },
                    "coins": {
                        "BTC": {
                            "name": "Bitcoin",
                            "withdraw": "ON",
                            "deposit": "ON"
                        },
                        "ETH": {
                            "name": "Ethereum",
                            "withdraw": "ON",
                            "deposit": "ON"
                        },
                    }
                }
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        """Overall tickers and assets info"""
        data = {}
        pairs_data = get_filtered_pairs_24h_stats(DISABLE_STACK)
        pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
        yesterday = now() - datetime.timedelta(hours=24)

        def id_filter(**kwargs):
            return ExecutionResult.objects.filter(
                **kwargs
            ).values(
                'pair'
            ).annotate(
                id=Max('id')
            ).values_list(
                'id', flat=True
            )

        prices_24h = {Pair.get(i['pair']).code: i['price'] for i in
                      ExecutionResult.objects.filter(
                          id__in=id_filter(updated__lte=yesterday)
                      ).values('pair', 'price')}

        high_low_qs = ExecutionResult.objects.filter(
            updated__gt=yesterday,
            cancelled=False,
        ).values(
            'pair'
        ).annotate(
            high=Max('price'),
            low=Min('price'),
        )
        high_lows_dict = {Pair.get(i['pair']): i for i in high_low_qs}

        for pair in Pair.objects.all():
            if is_pair_disabled(pair, DISABLE_STACK):
                continue

            result = {
                'last_price': 0.0,
                'high_24h': 0.0,
                'low_24h': 0.0,
                'base_volume': 0.0,
                'quote_volume': 0.0,
                'lowest_ask': 0.0,
                'highest_bid': 0.0,
                'percent_change': 0.0,
                'is_frozen': 0
            }

            pair_data = pairs_data.get(pair.code, {})

            pair = Pair.get(pair)

            last_price = pair_data.get('price') or 0
            price_24h = prices_24h.get(pair.code, 0.0)

            if last_price:
                result['last_price'] = last_price

            if last_price and price_24h:
                result['percent_change'] = (last_price - price_24h) / price_24h

            high_low = high_lows_dict.get(pair) or {}

            result['quote_volume'] = pair_data.get('volume') or 0
            result['base_volume'] = pair_data.get('base_volume') or 0
            result['high_24h'] = high_low.get('high')
            result['low_24h'] = high_low.get('low')

            stack_data = StackView.stack_limited(pair, 1, 1)
            if stack_data:
                result['lowest_ask'] = stack_data.get('top_sell', [])
                result['highest_bid'] = stack_data.get('top_buy', [])

            key = f'{pair.base.code}_{pair.quote.code}'
            data[key] = result

        coins = {}
        coins_info = CoinInfo.get_coins_info()
        for symbol, coin in coins_info.items():
            if DisabledCoin.is_coin_disabled(symbol, DISABLE_STACK):
                continue
            coins[symbol] = {
                'name': coin.get('name', ''),
                'withdraw': 'ON',
                'deposit': 'ON'
            }

        response = {
            'data': data,
            'coins': coins
        }

        return Response(response, status=status.HTTP_200_OK)


@extend_schema(exclude=True)
@api_view(['GET'])
@permission_classes((AllowAny,))
def get_otc_price(request):
    from core.otcupdater import OtcOrdersUpdater
    pair_code = request.GET.get('pair', 'BTC-USD')
    bfx_price = to_decimal(OtcOrdersUpdater.get_cached_price(pair_code))
    return Response({'price': bfx_price}, status=status.HTTP_200_OK)


class PairsListView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(exclude=True)
    def get(self, request):
        """Returns pairs data"""
        return Response({'data': PairSettings.get_enabled_pairs_data()})


class MarketsListView(NoAuthMixin, ThrottlingViewMixin, APIView):
    http_method_names = ['get']

    @extend_schema(exclude=True)
    def get(self, request):
        """Returns available markets"""
        r = [i.to_dict() for i in Pair.objects.all() if i.code not in PairSettings.get_disabled_pairs()]
        r = [{
            'id': i['code'],
            'base': i['base']['code'],
            'quote': i['quote']['code'],
            'type': 'spot',
        } for i in r]
        return Response(r)


class OrderBookView(NoAuthMixin, ThrottlingViewMixin, APIView):
    @extend_schema(
        summary='Orderbook',
        description='Orderbook for selected pair',
        parameters=[
            OpenApiParameter(name='depth', type=int, description='Number of entries. 100 by default, max. 500'),
        ],
        examples=[
            OpenApiExample(
                'Response Example',
                value={
                    "timestamp": 1569313042682,
                    "asks": [
                        [
                            9733.685,
                            0.00037616
                        ]
                    ],
                    "bids": [
                        [
                            9733.183,
                            0.00030966
                        ]
                    ]
                }
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, pair):
        """Returns orderbook for selected pair"""
        pair = pair.replace('_', '-')
        request_data = {
            'pair': pair,
            'depth': request.GET.get('depth', 100)
        }
        serializer = PairLimitValidationSerializer(data=request_data)
        serializer.is_valid(raise_exception=True)

        pair = Pair.get(pair)
        if is_pair_disabled(pair, DISABLE_STACK):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        depth = int(request.GET.get('depth', 100))
        data = StackView.stack_limited(pair, depth, depth)
        response = {
            'timestamp': int(round(time.time() * 1000)),
            'asks': [[i['price'], i['quantity']] for i in StackView.group(data['sells'])],
            'bids': [[i['price'], i['quantity']] for i in StackView.group(data['buys'], reverse=True)]
        }
        return Response(response, status=status.HTTP_200_OK)


class TradesView(NoAuthMixin, ThrottlingViewMixin, APIView):
    @extend_schema(
        summary='Trades history',
        description='Trades history for selected pair',
        examples=[
            OpenApiExample(
                'Response Example',
                value=[
                    {
                        "trade_id": 30694469,
                        "price": 9724.14488444,
                        "base_volume": 0.00038326,
                        "quote_volume": 3.7268757684104745,
                        "trade_timestamp": 1569313098,
                        "type": "buy"
                    },
                    {
                        "trade_id": 30694467,
                        "price": 9725.14002299,
                        "base_volume": 0.00034305,
                        "quote_volume": 3.3362092848867193,
                        "trade_timestamp": 1569313098,
                        "type": "sell"
                    },
                ]
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, pair):
        """Returns trades history for selected pair"""
        pair = pair.replace('_', '-')
        request_data = {
            'pair': pair
        }
        serializer = PairLimitValidationSerializer(data=request_data)
        serializer.is_valid(raise_exception=True)

        pair = Pair.get(pair)
        if is_pair_disabled(pair, DISABLE_STACK):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        depth = 200
        result = ExecutionResult.objects.filter(
            pair=pair
        ).select_related(
            'matched_order'
        ).only(
            'id',
            'matched_order_id',
            'quantity',
            'price',
            'created',
        ).annotate(
            order_gt=F('order_id') - F('matched_order_id'),
        ).filter(
            cancelled=False,
            order_gt__gt=0,
        ).order_by('-id')
        result = result[:depth]
        data = ExecutionResultSerializer(result, many=True).data
        return Response(data, status=status.HTTP_200_OK)


######## REQUIRES API KEY #############

class BalancesListView(ThrottlingViewMixin, APIView):
    authentication_classes = (HMACAuthentication,)

    @extend_schema(
        summary='Wallets balances',
        description='Wallets balances',
        examples=[
            OpenApiExample(
                'Response Example',
                value={
                    "BTC": {
                        "actual": 73.59451,
                        "orders": 0.40877
                    },
                    "EUR": {
                        "actual": 9821.53659869,
                        "orders": 88.51722622
                    },
                    "USD": {
                        "actual": 100078.73854682,
                        "orders": 6.61468349
                    },
                }
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, currency=None):
        """Returns user's balances. Requires API-KEY"""
        balances = Balance.for_user(request.user, currency)
        return Response(balances, status=status.HTTP_200_OK)


@extend_schema_view(
    create=extend_schema(
        summary='Create order',
        description='Creates new order. Only orders with types 0(Limit), 2(External) available',
        request=LimitOnlyOrderSerializer,
        responses=LimitOnlyOrderSerializer,
    ),
    destroy=extend_schema(summary='Cancel order', description='Cancel order'),
    list=extend_schema(
        summary='Orders list',
        description='Returns orders list',
        responses=LimitOnlyOrderSerializer
    ),
    retrieve=extend_schema(
        summary='Order details',
        description='Returns selected order',
        responses=LimitOnlyOrderSerializer
    ),
)
class OrdersApiViewSet(ThrottlingViewMixin, OrdersView):
    authentication_classes = (HMACAuthentication,)


@extend_schema_view(
    post=extend_schema(summary='Update order', description='Updates order', request=UpdateOrderSerializer)
)
class OrderUpdateApiView(ThrottlingViewMixin, OrderUpdateView):
    authentication_classes = (HMACAuthentication,)


@extend_schema(exclude=True)
@api_view(['GET'])
@permission_classes((AllowAny,))
def render_docs(request):
    md_file_path = os.path.join(settings.BASE_DIR, 'public_api/docs/api.md')
    with open(md_file_path, 'r') as f:
        md_content = f.read()
    html = markdown.markdown(md_content, extensions=['extra', 'codehilite', 'attr_list', 'def_list'])
    return render(request, 'api/docs.html', {"html": html})


@extend_schema(exclude=True)
@api_view(['GET'])
@permission_classes((AllowAny,))
def server_time(request):
    return Response({'server_time': int(time.time() * 1000)}, status=status.HTTP_200_OK)
