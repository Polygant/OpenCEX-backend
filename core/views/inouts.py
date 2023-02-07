import logging

from django.conf import settings
from django.db.models import Q
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter, extend_schema_view
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.consts.currencies import CURRENCIES_LIST
from core.consts.inouts import CANCELLED
from core.currency import Currency
from core.lib.inouts import BasePayGate
from core.models.inouts.balance import Balance
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.inouts.fees_and_limits import FeesAndLimits
from core.models.inouts.fees_and_limits import WithdrawalFee
from core.models.inouts.sci import GATES, PayGateTopup, name2id
from core.models.inouts.transaction import Transaction
from core.models.inouts.withdrawal import WithdrawalRequest
from core.serializers.inouts import LastCryptoWithdrawalAddressesSerializer, TopupSerializer
from core.serializers.inouts import TransactionSerizalizer
from lib.filterbackend import FilterBackend
from lib.utils import generate_random_string

log = logging.getLogger(__name__)


class BalanceView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ['get']

    @extend_schema(
        description='Perform balance data',
        # request=TransactionSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "balance": {
                        "BTC": {
                            "actual": 0,
                            "orders": 0
                        },
                        "ETH": {
                            "actual": 0,
                            "orders": 0
                        },
                        "USDT": {
                            "actual": 0,
                            "orders": 0
                        },
                        "<currency>": {
                            "actual": 0,
                            "orders": 0
                        },
                    }
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        if request.user.is_anonymous:
            return Response({'balance': {}})

        return Response({'balance': Balance.for_user(request.user)})


class BalanceByCurrencyView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        description='Perform balance data by currency',
        # request=TransactionSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "balance": {
                        "actual": 0,
                        "orders": 0,
                        "currency": "<currency>",
                    }
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request, currency=None):
        if request.user.is_anonymous:
            return Response({'balance': {}})

        currency_model = Currency.get(currency)
        return Response({'balance': Balance.for_user(request.user, currency_model)})


class PortfolioBalanceView(APIView):
    http_method_names = ['get']

    @extend_schema(
        description='Perform portfolio balance data',
        parameters=[
            OpenApiParameter(
                required=True,
                name='currency',
                type=str,
                description='currency code.',
                default='USDT',
                enum=[i[1] for i in CURRENCIES_LIST],
            ),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "balance": {
                        "<currency>": {
                            "actual": 0,
                            "orders": 0,
                            "price": 0,
                            "price_24h": 0,
                            "price_24h_value": 0,
                            "actual_usd": 0,
                        },
                    }
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        currency = request.GET.get('currency', 'USDT')
        currency = Currency.get(currency)
        result = Balance.portfolio_for_user(request.user, currency.code)
        return Response({'balance': result})


class TransactionsFilter(filters.FilterSet):
    currency = filters.Filter(name='currency', method='filter_currency')
    wallet = filters.Filter(name='wallet', method='filter_wallet')

    def filter_currency(self, queryset, name, value):
        value = Currency.get(value)
        return queryset.filter(**{name: value})

    def filter_wallet(self, queryset, name, value):
        if value:
            return queryset.filter(reason__in=[1, 2, 20, 21])
        else:
            return queryset.all()

    class Meta:
        model = Transaction
        fields = ('state', 'reason', 'currency')


class TransactionsView(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerizalizer
    queryset = Transaction.objects.all()
    filter_backends = (FilterBackend,)
    filter_class = TransactionsFilter

    def get_queryset(self):
        qs = super(TransactionsView, self).get_queryset().order_by('-id')

        return qs.filter(user=self.request.user).filter((~Q(state=CANCELLED)))


class LastCryptoWithdrawalAddressesList(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    @extend_schema(
        description='Perform data',
        responses={
            200: OpenApiResponse(response=LastCryptoWithdrawalAddressesSerializer(many=True))
        },
    )
    def get(self, request):
        # get present currencies
        currencies = WithdrawalRequest.objects.filter(
            user=request.user,
            data__icontains='destination',
        ).values_list(
            'currency',
            flat=True,
        ).distinct(
            'currency',
        )

        results = []
        for currency in currencies:
            qs = WithdrawalRequest.objects.filter(
                user=request.user,
                currency=currency,
                data__icontains='destination',
            ).values_list(
                'data',
                flat=True,
            ).distinct(
                'data',  # i hope data contains only 'destination' attr
            )
            addresses = []
            for item in qs:
                addr = item.get('destination')
                addresses.append(addr)

            addresses = reversed(addresses[:settings.LAST_CRYPTO_WITHDRAWAL_ADDRESSES_COUNT])

            results.append({
                'currency': currency,
                'addresses': addresses,
            })

        serializer = LastCryptoWithdrawalAddressesSerializer(results, many=True)

        return Response(serializer.data)


class CoinsStatusView(GenericAPIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        description='Perform data',
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "BTC": {
                        "disable_topups": "<bool>",
                        "disable_withdrawals": "<bool>",
                        "disable_exchange": "<bool>",
                        "disable_pairs": "<bool>",
                        "disable_stack": "<bool>",
                        "disable_all": "<bool>"
                    },
                    "<currency>": {
                        "disable_topups": "<bool>",
                        "disable_withdrawals": "<bool>",
                        "disable_exchange": "<bool>",
                        "disable_pairs": "<bool>",
                        "disable_stack": "<bool>",
                        "disable_all": "<bool>"
                    },
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        coins = DisabledCoin.get_coins_status()
        if not request.user.is_anonymous:
            for coin, restrictions in coins.items():
                restrictions['disable_topups'] = restrictions['disable_topups'] \
                                                 or request.user.restrictions.disable_topups
                restrictions['disable_withdrawals'] = restrictions['disable_withdrawals'] \
                                                      or request.user.restrictions.disable_withdrawals
        return Response(status=status.HTTP_200_OK, data=coins)


class FeesLimitsView(GenericAPIView):
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
                    "<currency>": {
                        "limits": {
                            "deposit": {
                                "min": 0.0001,
                                "max": 1000.0
                            },
                            "withdrawal": {
                                "min": 0.0001,
                                "max": 15.0
                            },
                            "order": {
                                "min": 0.001,
                                "max": 15.0
                            },
                            "code": {
                                "max": 100.0
                            },
                            "accumulation": {
                                "min": 0.001
                            }
                        },
                        "fee": {
                            "deposit": {
                                "address": 1e-07,
                                "code": 0.0
                            },
                            "withdrawal": {
                                "address": {
                                    "<currency>": 1e-07
                                },
                                "code": 0.0
                            },
                            "order": {
                                "limit": 0.001,
                                "market": 0.002
                            },
                            "exchange": {
                                "value": 0.002
                            }
                        }
                    },
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        fl = FeesAndLimits.get_fees_and_limits()
        return Response(status=status.HTTP_200_OK, data=fl)


class WithdrawalFeeView(GenericAPIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        responses={
            200: OpenApiTypes.STR
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'BTC': 0,
                    '<currency>': 0,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request, currency):
        try:
            curr = Currency.get(currency)
            fee = WithdrawalFee.get_blockchains_by_currency(curr)
            return Response(status=status.HTTP_200_OK, data=fee)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': str(e)})


def generate_remittance_id():
    return generate_random_string(length=12).upper()


@extend_schema_view(
    post=extend_schema(
        responses={
            200: OpenApiTypes.STR
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value='OK',
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    ),
    get=extend_schema(
        responses={
            200: OpenApiTypes.STR
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value='OK',
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    ),
)
@api_view(['POST', 'GET'])
@permission_classes((AllowAny,))
def interaction(request, gate_name):
    if request.method == 'GET':
        data = {i: request.GET[i] for i in request.GET.keys()}
    else:
        data = {i: request.data[i] for i in request.data.keys()}

    gate_id = gate_name if gate_name.isdigit() else name2id(gate_name)
    PayGateTopup.update_from_notification(gate_id, data)
    return Response('OK', status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(exclude=True,),
    get=extend_schema(exclude=True,),
)
@api_view(['POST', 'GET'])
@permission_classes((AllowAny,))
def interaction_dev(request, gate_name):
    if settings.DEBUG is False:
        return Response('Disabled in prod mode', status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        data = request.GET
    else:
        data = request.data

    gate_id = gate_name if gate_name.isdigit() else name2id(gate_name)

    PayGateTopup.update_from_notification(gate_id, data)
    return Response({'status': True}, status=status.HTTP_200_OK)


class TopupRequestView(viewsets.ReadOnlyModelViewSet, viewsets.mixins.CreateModelMixin):
    serializer_class = TopupSerializer
    queryset = PayGateTopup.objects.all()
    filter_backends = (FilterBackend,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = None

    def get_queryset(self):
        qs = super(TopupRequestView, self).get_queryset()
        return qs.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.instance: PayGateTopup = self.perform_create(serializer)

        response = Response({
            'url': self.instance.topup_url,
            'id': self.instance.id,
        }, status=status.HTTP_201_CREATED)
        return response

    def perform_create(self, serializer):
        self.instance = serializer.save()
        return self.instance


@extend_schema_view(
    post=extend_schema(
        description='Check top-up status.',
        parameters=[
            OpenApiParameter(required=True, name='gate_id', type=int,),
            OpenApiParameter(required=True, name='id', type=str,),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'state': '<int: PENDING:0|COMPLETED:1|FAILED:2>',
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def check_status_topup(request):
    try:
        gate_id = int(request.data.get('gate_id'))
    except (ValueError, TypeError):
        # TODO error_format
        raise ValidationError('Field "gate_id" required!')

    if gate_id not in GATES:
        return Response(status=status.HTTP_404_NOT_FOUND)

    gate: BasePayGate = GATES[gate_id]

    pk = request.data.get('id')

    if pk is None:
        # TODO error_format
        raise ValidationError('Field "id" required!')

    if gate.NAME == 'cauri':
        pk = pk[2:]

    topup: PayGateTopup = PayGateTopup.objects.filter(user=request.user, gate_id=gate_id, pk=pk).first()
    if topup is not None:
        return Response(data={
            'state': topup.state,
        })

    return Response(status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
    post=extend_schema(
        description='Calculate topup fee depending of paygate.',
        parameters=[
            OpenApiParameter(required=True, name='gate_id', type=int,),
            OpenApiParameter(required=True, name='target_amount', type=float,),
            OpenApiParameter(required=True, name='currency', type=str,),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'amount': 0,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def topup_amount(request):
    """
    Calculate topup fee depending of paygate.
    """
    try:
        gate_id = int(request.data.get('gate_id'))
    except (ValueError, TypeError):
        # TODO error_format
        raise ValidationError('Invalid gate id')

    if gate_id not in GATES:
        return Response(status=status.HTTP_404_NOT_FOUND)

    gate = GATES[gate_id]

    # TODO: sci/topup_amount - refactoring for all gates
    # only Cauri supported for now
    if gate.NAME == 'cauri':
        amount = gate.get_topup_amount(
            target_amount=request.data.get('target_amount'),
            currency_symbol=request.data.get('currency'),
        )
        return Response(data={
            'amount': amount,
        })

    return Response(status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
    post=extend_schema(
        description='Calculate withdrawal fee depending of paygate.',
        parameters=[
            OpenApiParameter(required=True, name='gate_id', type=int,),
            OpenApiParameter(required=True, name='target_amount', type=float,),
            OpenApiParameter(required=True, name='currency', type=str,),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'amount': 0,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def withdraw_amount(request):
    """
    Calculate withdrawal fee depending of paygate.
    """
    try:
        gate_id = int(request.data.get('gate_id'))
    except (ValueError, TypeError):
        # TODO error_format
        raise ValidationError('Invalid gate id')

    if gate_id not in GATES:
        return Response(status=status.HTTP_404_NOT_FOUND)

    gate = GATES[gate_id]

    # TODO: sci/withdrawal_amount - refactoring for all gates
    # only WinPay supported for now
    if gate.NAME == 'win_pay':
        amount = gate.get_withdrawal_amount(
            target_amount=request.data.get('target_amount'),
            currency_symbol=request.data.get('currency'),
        )
        return Response(data={
            'amount': amount,
        })

    return Response(status=status.HTTP_404_NOT_FOUND)
