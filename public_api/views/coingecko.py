import datetime
import logging
import os
import time
from itertools import groupby

import markdown
from django.conf import settings
from django.db.models import F
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
from django.shortcuts import render
from django.utils.timezone import now
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import PairSettings
from core.models.orders import ExecutionResult
from core.models.inouts.pair import Pair
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from core.views.orders import StackView
from lib.throttling import RedisCacheAnonRateThrottle, RedisCacheUserRateThrottle
from public_api.serializers.coingecko import ExecutionResultSerializer
from public_api.serializers.coingecko import PairLimitValidationSerializer
from public_api.utils import is_pair_disabled

log = logging.getLogger(__name__)


class PairsListView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ['get']
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        r = list([{
            'ticker_id': f'{i.base.code}_{i.quote.code}',
            'base': i.base.code,
            'target': i.quote.code
        } for i in Pair.objects.all() if i.code not in PairSettings.get_disabled_pairs()])
        return Response(r)


class TickersView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ['get']
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        data = []
        pairs_data = get_filtered_pairs_24h_stats()
        pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
        yesterday = now() - datetime.timedelta(hours=24)

        for pair in Pair.objects.all():
            if is_pair_disabled(pair):
                continue

            pair_data = pairs_data.get(pair.code, {})
            result = {
                'ticker_id': f'{pair.base.code}_{pair.quote.code}',
                'base_currency': pair.base.code,
                'target_currency': pair.quote.code,
                'last_price': pair_data.get('price'),
                'base_volume': pair_data.get('base_volume') or 0.0,
                'target_volume': pair_data.get('volume') or 0.0,
                'ask': 0.0,
                'bid': 0.0,
                'high': 0.0,
                'low': 0.0,
            }

            pair = Pair.get(pair)
            qs = ExecutionResult.objects.filter(
                pair=pair,
                cancelled=False
            ).select_related('order')

            aggregation = qs.filter(
                updated__gte=yesterday
            ).aggregate(
                high_24h=Max(F('price')),
                low_24h=Min(F('price')),
            )

            result['high'] = aggregation['high_24h']
            result['low'] = aggregation['low_24h']

            stack_data = StackView.stack_limited(pair, 1, 1)
            if stack_data:
                result['ask'] = stack_data.get('top_sell', [])
                result['bid'] = stack_data.get('top_buy', [])

            data.append(result)

        return Response(data, status=status.HTTP_200_OK)


class OrderBookView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        ticker_id = request.GET.get('ticker_id', '').replace('_', '-')
        request_data = {
            'ticker_id': ticker_id,
            'depth': request.GET.get('depth', 100)
        }
        serializer = PairLimitValidationSerializer(data=request_data)
        serializer.is_valid(raise_exception=True)

        pair = Pair.get(ticker_id)
        if is_pair_disabled(pair):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        depth = int(request.GET.get('depth', 100))
        data = StackView.stack_limited(ticker_id, depth, depth)
        response = {
            'ticker_id': ticker_id,
            'timestamp': int(round(time.time() * 1000)),
            'asks': [[i['price'], i['quantity']] for i in StackView.group(data['sells'])],
            'bids': [[i['price'], i['quantity']] for i in StackView.group(data['buys'])]
        }
        return Response(response, status=status.HTTP_200_OK)


class TradesView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        ticker_id = request.GET.get('ticker_id', '').replace('_', '-')
        o_type = request.GET.get('type', '')

        request_data = {
            'ticker_id': ticker_id,
            'type': o_type
        }
        serializer = PairLimitValidationSerializer(data=request_data)
        serializer.is_valid(raise_exception=True)

        pair = Pair.get(ticker_id)
        if is_pair_disabled(pair):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        depth = 200
        result = ExecutionResult.objects.filter(
            pair=ticker_id
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

        if o_type:
            result = result.filter(
                matched_order__operation=(1 if o_type == 'sell' else 0)
            )
        result = result[:depth]
        data = ExecutionResultSerializer(result, many=True).data

        grouper = lambda item: item['type']
        data = sorted(data, key=grouper)
        res = {key: list(group_items) for key, group_items in groupby(data, key=grouper)}

        return Response(res, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes((AllowAny,))
def render_docs(request):
    md_file_path = os.path.join(settings.BASE_DIR, 'public_api/docs/coingecko_api.md')
    with open(md_file_path, 'r') as f:
        md_content = f.read()
    html = markdown.markdown(md_content, extensions=['extra', 'codehilite', 'attr_list', 'def_list'])
    return render(request, 'api/docs.html', {"html": html})
