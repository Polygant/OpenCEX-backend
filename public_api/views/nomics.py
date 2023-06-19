import logging

from django.db.models import F
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models.orders import ExecutionResult
from core.models.inouts.pair import Pair
from core.views.orders import StackView
from lib.helpers import get_iso_dt
from lib.throttling import RedisCacheAnonRateThrottle, RedisCacheUserRateThrottle
from public_api.serializers.nomics import ExecutionResultSerializer
from public_api.serializers.nomics import PairLimitValidationSerializer
from public_api.utils import is_pair_disabled

log = logging.getLogger(__name__)


class TradesViewNomics(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        serializer = PairLimitValidationSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        pair = request.GET.get('market')
        try:
            since = int(request.GET.get('since', 0))
        except:
            since = None

        pair = Pair.get(pair)
        if is_pair_disabled(pair):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        result = ExecutionResult.objects.filter(
            pair=pair
        ).select_related(
            'order'
        ).only(
            'id',
            'order_id',
            'matched_order_id',
            'quantity',
            'price',
            'created',
            'order__id'
        ).annotate(
            order_gt=F('order_id') - F('matched_order_id'),
        ).filter(
            cancelled=False,
            order_gt__gt=0,
        ).order_by('id')

        if since:
            result = result.filter(id__gt=since)
        else:
            result = result[:100]
        serializer = ExecutionResultSerializer(result, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderBookView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (
        RedisCacheAnonRateThrottle,
        RedisCacheUserRateThrottle,
    )

    def get(self, request):
        serializer = PairLimitValidationSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        pair = request.GET.get('market')

        pair = Pair.get(pair)
        if is_pair_disabled(pair):
            raise ValidationError({'ticker_id': 'Pair is unavailable'})

        limit = 100
        data = StackView.stack_limited(pair, limit, limit)
        response = {
            'timestamp': get_iso_dt(),
            'asks': [[i['price'], i['quantity']] for i in StackView.group(data['sells'])],
            'bids': [[i['price'], i['quantity']] for i in StackView.group(data['buys'], reverse=True)]
        }
        return Response(response, status=status.HTTP_200_OK)
