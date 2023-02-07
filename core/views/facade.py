import hashlib
import hmac
import logging
from datetime import datetime
from time import time

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import translation, timezone
from django.utils.timezone import now
from django_countries import countries
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiExample, OpenApiParameter
from ipware import get_client_ip
from rest_framework import status
from rest_framework import views, viewsets
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import RetrieveModelMixin, CreateModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.cache import facade_cache, RESEND_VERIFICATION_TOKEN_CACHE_KEY
from core.consts.facade import COMMON_COINS_INFO
from core.consts.orders import BUY
from core.exceptions.facade import BadSecret
from core.exceptions.facade import SOFAlreadySetError
from core.models.facade import Message, CoinInfo, SmsConfirmationHistory
from core.models.facade import Profile
from core.models.facade import SourceOfFunds
from core.models.facade import TwoFactorSecretTokens
from core.models.facade import UserKYC
from core.models.inouts.disabled_coin import DisabledCoin
from core.models.orders import ExecutionResult
from core.serializers.auth import UserProfileSerializer, CaptchaProcessor
from core.serializers.facade import MessageSerializer
from core.serializers.facade import SourceOfFundsSerializer
from core.tasks.facade import notify_sof_verification_request_admin
from core.utils.facade import generate_sitemap
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from lib.filterbackend import FilterBackend
from lib.services.sumsub_client import SumSubClient
from lib.services.twilio import TwilioClient
from lib.services.twilio import twilio_client
from lib.throttling import PhoneVerificationThrottle
from lib.utils import render
from lib.views import ExceptionHandlerMixin

logger = logging.getLogger(__name__)


@extend_schema_view(
    post=extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response base',
                value={
                    'token': '<str>',
                    'userId': '<str>',
                },
                request_only=False,
                response_only=True,
            ),
        ]
    )
)
@api_view(['POST'])
def kyc_get_access_token(request):
    if not settings.IS_KYC_ENABLED:
        return Response(status=status.HTTP_403_FORBIDDEN)

    usr_email = request.user.email
    client = SumSubClient(host='https://test-api.sumsub.com' if settings.DEBUG else SumSubClient.HOST)
    result = client.get_acces_token(usr_email)
    return Response(status=status.HTTP_200_OK, data=result)


@extend_schema_view(
    post=extend_schema(exclude=True),
)
@api_view(['POST'])
@permission_classes((AllowAny,))
def kyc_callback_url(request):
    validation_token = request.headers.get('X-Payload-Digest')
    calculated_token = hmac.new(
        settings.SUMSUM_CALLBACK_VALIDATION_SECRET.encode('utf-8'),
        request.body,
        digestmod=hashlib.sha1
    ).hexdigest()

    if validation_token != calculated_token:
        return

    data = request.data
    type_callback = data.get('type')

    if type_callback and type_callback == 'applicantReviewed':
        apId = data['applicantId']
        moderationComment = data['reviewResult'].get('moderationComment')
        revAns = data['reviewResult']['reviewAnswer']

        revType = None
        revLabels = None
        if revAns == UserKYC.ANSWER_RED:
            revType = data['reviewResult'].get('reviewRejectType')
            revLabels = data['reviewResult'].get('rejectLabels')

        usr_email = data['externalUserId']

        usr = User.objects.get(username=usr_email)

        params = {
            'rejectType': revType,
            'applicantId': apId,
            'moderationComment': moderationComment,
            'rejectLabels': revLabels,
            'kyc_data': data,
            'last_kyc_data_update': timezone.now()
        }

        if revAns in [UserKYC.ANSWER_GREEN, UserKYC.ANSWER_RED]:
            params['reviewAnswer'] = revAns

        UserKYC.objects.filter(user=usr).update(**params)

    else:
        logger.info(f'#kyc_callback_url data: %s', data)

    return Response(status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response base',
                value={
                    'kyc_answer': '<str>'
                },
                request_only=False,
                response_only=True,
            ),
            OpenApiExample(
                'Example ON',
                summary='response GREEN',
                value={
                    'kyc_answer': UserKYC.ANSWER_GREEN
                },
                request_only=False,
                response_only=True,
            ),
            OpenApiExample(
                'Example OFF',
                summary='response RED',
                value={
                    'kyc_answer': UserKYC.ANSWER_RED
                },
                request_only=False,
                response_only=True,
            ),
        ]
    )
)
@api_view(['POST'])
def check_kyc_verification(request):
    # simple patch to not modify front for this time
    result = None
    user_kyc: UserKYC = UserKYC.objects.filter(user=request.user).first()
    if user_kyc:
        if user_kyc.forced_approve:
            result = UserKYC.ANSWER_GREEN
        else:
            result = user_kyc.reviewAnswer

    return Response(status=status.HTTP_200_OK, data={'kyc_answer': result})


class MessagesView(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = MessageSerializer
    queryset = Message.objects.order_by('-created')

    filter_backends = (FilterBackend,)
    filterset_fields = ('read',)

    def get_queryset(self):
        qs = super(MessagesView, self).get_queryset()
        if self.request.user.is_anonymous:
            return qs.filter(user_id=0)
        return qs.filter(user=self.request.user)


@extend_schema_view(
    post=extend_schema(
        parameters=[
            OpenApiParameter(required=True, name='id', type=int, description='Message id.'),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={'result': 'ok'},
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def mark_message_as_read(request):
    msg_id = request.data.get('id', None)
    if msg_id:
        Message.objects.filter(
            user_id=request.user.id,
            read=False,
            id=msg_id).update(
            read=True)
    return Response(data={'result': 'ok'})


class CountryList(views.APIView):
    permission_classes = [
        AllowAny,
    ]

    @extend_schema(
        description='Perform data',
        # request=TransactionSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "AF": "Afghanistan",
                    "AX": "Åland Islands",
                    "AL": "Albania",
                    "DZ": "Algeria",
                    "AS": "American Samoa",
                    "AD": "Andorra",
                    "<country_code>": "<country_name>",
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        lang = request.GET.get('lang', 'en')
        translation.activate(lang)
        request.LANGUAGE_CODE = translation.get_language()
        return Response(data=countries)


class UserProfileView(RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserProfileSerializer
    queryset = Profile.objects.all()

    def get_queryset(self):
        qs = super(UserProfileView, self).get_queryset()
        return qs.filter(user=self.request.user)

    def get_object(self):
        return self.get_queryset().first()


class RegenerateApiKey(views.APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        exclude=True,
    )
    def post(self, request):
        profile = request.user.profile
        profile.regenerate_keys()
        return Response(data={
            'api_key': profile.api_key,
            'secret_key': profile.secret_key,
        })


class PhoneVerification(views.APIView):
    throttle_classes = (PhoneVerificationThrottle,)
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                required=True,
                name='phone',
                type=str,
                description='phone number.'
            ),
            OpenApiParameter(
                required=True,
                name='verify',
                type=str,
                description='verify type.',
                default=TwilioClient.TYPE_PHONE,
                enum=TwilioClient.VERIFICATION_TYPES,
            ),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='success response',
                value={
                    "result": "<bool>",
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
            OpenApiExample(
                'Example',
                summary='error response',
                value={
                    "result": "<bool>",
                    "error": "<str>",
                    "extra": {
                        "ts": "<int>",
                        "timeout": "<int>",
                    },
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def post(self, request):
        if settings.IS_SMS_ENABLED:
            return Response(status=status.HTTP_403_FORBIDDEN)

        user = request.user

        phone = request.data.get('phone')
        verification_type = request.data.get('verify', TwilioClient.TYPE_PHONE)

        if verification_type not in TwilioClient.VERIFICATION_TYPES:
            raise ValidationError({
                'message': 'Incorrect verification type!!',
                'type': 'incorrect_verification_type'
            })

        if not phone:
            # TODO error_format
            raise ValidationError()

        data = {
            'result': False
        }

        cache_key = f'{verification_type}-verify-{user.id}'
        cache_val = facade_cache.get(cache_key)
        ts_now = int(time())

        if not cache_val:
            history_entry = SmsConfirmationHistory.objects.create(
                user=user,
                phone=phone,
                action_type=SmsConfirmationHistory.ACTION_TYPE_SEND_SMS,
                verification_type=twilio_client.verification_type_to_int(verification_type),
            )
            is_send = twilio_client.verify_sms(phone, verification_type)
            if is_send:
                history_entry.success()
                data['result'] = is_send
                facade_cache.set(cache_key, ts_now + 60, timeout=60)
        else:
            data['error'] = 'timeout'
            data['extra'] = {
                'ts': cache_val,
                'timeout': cache_val - ts_now
            }

        return Response(data=data)


class CodePhoneVerification(views.APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                required=True,
                name='phone',
                type=str,
                description='phone number.'
            ),
            OpenApiParameter(
                required=True,
                name='verify',
                type=str,
                description='verify type.',
                default=TwilioClient.TYPE_PHONE,
                enum=TwilioClient.VERIFICATION_TYPES,
            ),
            OpenApiParameter(
                required=True,
                name='code',
                type=str,
                description='verify code.',
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
                    "status": "<bool>",
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def post(self, request):
        if settings.IS_SMS_ENABLED:
            return Response(status=status.HTTP_403_FORBIDDEN)

        profile = request.user.profile
        phone = request.data.get('phone')
        code = request.data.get('code')
        verification_type = request.data.get('verify', 'phone')

        if verification_type in [
                TwilioClient.TYPE_DISABLE_SMS, TwilioClient.TYPE_WITHDRAWAL]:
            if not profile.phone:
                raise ValidationError({
                    'message': 'The phone number is not linked to the account!',
                    'type': 'user_phone_not_linked'
                })
            else:
                # use phone from backend
                phone = profile.phone

        if not phone:
            raise ValidationError('Field "Phone" required!')

        if not code:
            raise ValidationError('Field "Code" required!')

        if verification_type not in TwilioClient.VERIFICATION_TYPES:
            raise ValidationError({
                'message': 'Incorrect verification type!!',
                'type': 'incorrect_verification_type'
            })

        history_entry = SmsConfirmationHistory.objects.create(
            user=request.user,
            phone=phone,
            action_type=SmsConfirmationHistory.ACTION_TYPE_VERIFY_CODE,
            code=code,
            verification_type=twilio_client.verification_type_to_int(verification_type),
        )

        result = twilio_client.check_code(phone, code, verification_type)

        if result:
            history_entry.success()

            if verification_type == TwilioClient.TYPE_PHONE:
                profile.phone = phone
                profile.withdrawals_sms_confirmation = True
                profile.save()
            elif verification_type == TwilioClient.TYPE_DISABLE_SMS:
                profile.withdrawals_sms_confirmation = False
                profile.save()
            elif verification_type == TwilioClient.TYPE_WITHDRAWAL:
                pass
            else:
                raise ValidationError({
                    'message': 'Incorrect verification type!!',
                    'type': 'incorrect_verification_type'
                })

        return Response(data={
            'status': result
        })


@extend_schema_view(
    get=extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={
                  "commons": {
                    "blockchain_definitions": {
                      "ETH": "ERC-20",
                    },
                    "token_tx_explorers": {
                      "ETH": "https://etherscan.io/tx/",
                    }
                  },
                  "coins": {
                    "ETH": {
                      "name": "Ethereum",
                      "base": "<bool>",
                      "decimals": "<int>",
                      "index": "<int>",
                      "tx_explorer": "https://etherscan.io/tx/",
                      "links": {
                        "bt": {
                          "href": "https://bitcointalk.org/index.php?topic=428589.0",
                          "title": "BitcoinTalk"
                        },
                        "cmc": {
                          "href": "https://coinmarketcap.com/currencies/ethereum/",
                          "title": "CoinMarketCap"
                        },
                        "exp": {
                          "href": "https://etherscan.io/",
                          "title": "Explorer"
                        },
                        "official": {
                          "href": "http://ethereum.org",
                          "title": "ethereum.org"
                        }
                      },
                      "is_token": "<bool>",
                      "blockchain_list": [],
                      "disable_topups": "<bool>",
                      "disable_withdrawals": "<bool>",
                      "disable_exchange": "<bool>",
                      "disable_pairs": "<bool>",
                      "disable_stack": "<bool>",
                      "disable_all": "<bool>",
                      "disable_p2p_code": "<bool>",
                      "price": "<float>",
                      "volume": "<float>",
                      "price_24h": "<float>"
                    },
                    "BTC": {
                      "name": "Bitcoin",
                      "base": "<bool>",
                      "decimals": "<int>",
                      "index": "<int>",
                      "tx_explorer": "https://www.blockchain.com/btc/tx/",
                      "links": {
                        "bt": {
                          "href": "https://bitcointalk.org/index.php",
                          "title": "BitcoinTalk"
                        },
                        "cmc": {
                          "href": "https://coinmarketcap.com/currencies/bitcoin/",
                          "title": "CoinMarketCap"
                        },
                        "exp": {
                          "href": "https://www.blockchain.com/en/explorer",
                          "title": "Explorer"
                        },
                        "official": {
                          "href": "https://bitcoin.org",
                          "title": "bitcoin"
                        }
                      },
                      "is_token": "<bool>",
                      "blockchain_list": [],
                      "disable_topups": "<bool>",
                      "disable_withdrawals": "<bool>",
                      "disable_exchange": "<bool>",
                      "disable_pairs": "<bool>",
                      "disable_stack": "<bool>",
                      "disable_all": "<bool>",
                      "disable_p2p_code": "<bool>",
                      "price": "<float>",
                      "volume": "<float>",
                      "price_24h": "<float>",
                    },
                  },
                  "pairs_data": {
                    "BTC-USDT": {
                      "volume": "<float>",
                      "base_volume": "<float>",
                      "price": "<float>",
                      "price_24h": "<float>",
                      "price_24h_value": "<float>",
                      "pair": "BTC-USDT",
                      "pair_data": {
                        "id": "<int>",
                        "code": "BTC-USDT",
                        "base": {
                          "id": "<int>",
                          "code": "BTC",
                          "is_token": "<bool>",
                          "blockchain_list": []
                        },
                        "quote": {
                          "id": "<int>",
                          "code": "USDT",
                          "is_token": "<bool>",
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
                      }
                    },
                    "ETH-USDT": {
                      "volume": "<float>",
                      "base_volume": "<float>",
                      "price": "<float>",
                      "price_24h": "<float>",
                      "price_24h_value": "<float>",
                      "pair": "ETH-USDT",
                      "pair_data": {
                        "id": "<int>",
                        "code": "ETH-USDT",
                        "base": {
                          "id": "<int>",
                          "code": "ETH",
                          "is_token": "<bool>",
                          "blockchain_list": []
                        },
                        "quote": {
                          "id": "<int>",
                          "code": "USDT",
                          "is_token": "<bool>",
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
                      }
                    },
                  },
                  "langs": [
                    "ru",
                    "tr"
                  ]
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['GET'])
@permission_classes((AllowAny,))
def coins_api_view(request):
    lang = request.GET.get('locale', 'en')
    langs = [l[0] for l in settings.LANGUAGES]
    if lang in langs:
        langs.remove(lang)
    pairs_data = get_filtered_pairs_24h_stats()
    pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
    coins = {}

    d_coins = DisabledCoin.get_coins_status()

    coins_info = CoinInfo.get_coins_info()

    for ticker, coin in coins_info.items():
        #  skip disabled coins
        if DisabledCoin.is_coin_disabled(ticker):
            continue

        coin_item = coin
        d_coin = d_coins.get(ticker, {
            'disable_withdrawals': False,
            'disable_topups': False,
            'disable_exchange': False,
            'disable_pairs': False,
            'disable_stack': False,
            'disable_all': False
        })
        coin_item.update(d_coin)

        if pairs_data.get(ticker + '-USDT'):
            coin_item['price'] = pairs_data[ticker + '-USDT']['price']
            coin_item['volume'] = pairs_data[ticker + '-USDT']['volume']
            coin_item['price_24h'] = pairs_data[ticker + '-USDT']['price_24h']

        coins[ticker] = coin_item

    return Response(data={
        'commons': COMMON_COINS_INFO,
        'coins': coins,
        'pairs_data': pairs_data,
        'langs': langs,
    })


class SourceOfFundsViewSet(ExceptionHandlerMixin,
                           RetrieveModelMixin,
                           CreateModelMixin,
                           UpdateModelMixin,
                           GenericViewSet):
    serializer_class = SourceOfFundsSerializer
    permission_classes = (
        IsAuthenticated,
    )

    def create(self, request, *args, **kwargs):
        user = request.user
        source = request.GET.get('source', 'wallet')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # allow edit in debug mode
        sof = SourceOfFunds.get_by_user(request.user)
        if sof is None:
            self.perform_create(serializer)
        else:
            if sof.is_set() and not settings.DEBUG:
                raise SOFAlreadySetError()
            else:
                SourceOfFunds.objects.filter(
                    user=self.request.user).update(
                    **serializer.validated_data)

        headers = self.get_success_headers(serializer.data)
        notify_sof_verification_request_admin.apply_async([request.user.id])

        return Response(serializer.data,
                        status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user.id)

    def get_object(self):
        return SourceOfFunds.get_by_user(self.request.user)


@extend_schema_view(
    post=extend_schema(
        parameters=[
            OpenApiParameter(required=True, name='lang', type=str, description='Language code.', default='en'),
        ]
    )
)
@api_view(['POST'])
def save_user_language(request):
    lang = request.data.get('lang', 'en')
    if lang not in dict(settings.LANGUAGES):
        return Response(status=status.HTTP_400_BAD_REQUEST, data={
                        'result': f'Lang {lang} not found'})
    profile = request.user.profile
    profile.language = lang
    profile.save()
    return Response(status=status.HTTP_200_OK)


def robots(request):
    return render(request, 'robots.txt', content_type="text/plain")


def sitemap(request):
    sitemap = generate_sitemap()
    return HttpResponse(sitemap, content_type="text/xml")


class CaptchaCheck(views.APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={
                    'Status': True,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def post(self, request):
        data = request.data
        captcher = CaptchaProcessor(
            (data.get('email') or data.get('username')).lower(),
            get_client_ip(request)[0],
            data.get('captcha')
        )
        captcher.check()

        return Response({'Status': True}, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response base',
                value="<str>",
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
            OpenApiExample(
                'Example ON',
                summary='response ON',
                value="ON",
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
            OpenApiExample(
                'Example OFF',
                summary='response OFF',
                value="OFF",
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def check_user_2fa_is_on(request):
    return Response('ON' if TwoFactorSecretTokens.is_enabled_for_user(
        request.user) else 'OFF', status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        parameters=[
            OpenApiParameter(required=True, name='secretcode', type=str),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={'2fa_enabled': True},
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def set_user_2fa(request):
    TwoFactorSecretTokens.set_code(request.user, request.data['secretcode'])
    return Response({'2fa_enabled': True}, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        parameters=[
          OpenApiParameter(required=True, name='secretcode', type=str),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={
                    '2fa_enabled': '<bool>'
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def remove_user_2fa(request):
    try:
        TwoFactorSecretTokens.disable(request.user, request.data['secretcode'])
        return Response({'2fa_enabled': False}, status=status.HTTP_200_OK)
    except BadSecret:
        return Response(status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    post=extend_schema(
        parameters=[
          OpenApiParameter(required=True, name='code', type=str),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={
                    'Status': '<bool>'
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
            OpenApiExample(
                'Example Expire',
                summary='response Expire',
                value={
                    'Status': '<bool>',
                    'code': 'expire',
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def check_otp(request):
    cache_key = get_2fa_cache_key(request.user)
    secret = cache.get(cache_key)
    if not secret:
        return Response({'Status': False, 'code': 'expire'},
                        status=status.HTTP_200_OK)
    result = TwoFactorSecretTokens.check_g_otp(secret, request.data['code'])
    return Response({'Status': result}, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value="<str>",
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
def generate_secret(request):
    secret = TwoFactorSecretTokens.generate_secret()
    cache_key = get_2fa_cache_key(request.user)
    cache.set(cache_key, secret, 600)
    return Response(secret, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        parameters=[
          OpenApiParameter(required=True, name='token', type=str),
          OpenApiParameter(required=False, name='lang', type=str, default='en',),
        ],
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example base',
                summary='response',
                value={
                    'Status': '<bool>'
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['POST'])
@permission_classes((AllowAny, ))
def resend_email_confirmation_mail(request):
    token = request.data.get('token')
    if not token:
        return Response({'Status': False, 'code': 'Token not found'}, status=status.HTTP_400_BAD_REQUEST)

    user_id = cache.get(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{token}')
    if not user_id:
        return Response({'Status': False, 'code': 'Token not found'}, status=status.HTTP_400_BAD_REQUEST)

    # check if verification email in progress
    verification_in_progress = cache.get(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{user_id}')
    if verification_in_progress:
        return Response({'Status': False, 'code': 'Email confirmation in progress'}, status=status.HTTP_400_BAD_REQUEST)

    lang = request.data.get('lang', 'en')
    if lang not in dict(settings.LANGUAGES):
        return Response(status=status.HTTP_400_BAD_REQUEST, data={
            'result': f'Lang {lang} not found'})

    translation.activate(lang)
    request.LANGUAGE_CODE = translation.get_language()

    user = User.objects.get(id=user_id)
    email_address = EmailAddress.objects.get(
        user=user,
        email=user.email,
    )
    if email_address.verified:
        return Response({'Status': False, 'code': 'Email already verified'}, status=status.HTTP_400_BAD_REQUEST)
    email_address.send_confirmation(request)

    # set verification in progress by user id
    cache.set(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{user_id}', 1, timeout=300)  # 5 min for next attempt
    return Response({'Status': True}, status=status.HTTP_200_OK)


def get_2fa_cache_key(user):
    return 'user_2fa_secret_%s_%s' % (user.email, user.id)
