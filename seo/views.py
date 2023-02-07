import random

from django.conf import settings
from django.utils import translation
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiExample
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.consts.currencies import CURRENCIES_LIST
from core.models.facade import CoinInfo
from core.models.inouts.disabled_coin import DisabledCoin
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from lib.filterbackend import FilterBackend
from seo.models import CoinStaticPage
from seo.models import CoinStaticSubPage
from seo.models import Post, Tag, ContentPhoto
from seo.serializers import CoinStaticPageSerializer
from seo.serializers import CoinStaticSubPageSerializer
from seo.serializers import PostSerializer, TagSerializer, ContentPhotoSerializer


class PostApiView(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = PostSerializer
    queryset = Post.objects.all()
    lookup_url_kwarg = 'slug'

    filter_backends = (FilterBackend,)
    filterset_fields = ('tags',)

    def retrieve(self, request, *args, **kwargs):
        lang = request.GET.get('locale', 'en')
        self.lookup_field = 'slug_' + lang
        return super().retrieve(request, *args, **kwargs)


class PostSlugsApiView(viewsets.ReadOnlyModelViewSet):
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
                    "slugs": [
                        "<str>",
                    ]
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def list(self, request):
        return Response({'slugs': Post.get_slugs_list()})


class TagListApiView(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = TagSerializer
    pagination_class = None
    queryset = Tag.objects.all()


class ContentPhotoApiView(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = ContentPhotoSerializer
    pagination_class = None
    queryset = ContentPhoto.objects.all()


@extend_schema_view(
    get=extend_schema(
        description='Perform data',
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    "btc_usdt_price": 0,
                    "btc_usdt_percent": -100.0,
                    "btc_usdt_profit": -3450,
                    "pairs_data": {
                        "BTC-USDT": {
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
                    },
                    "type_human": 2,
                    "currency": "USDT"
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
)
@api_view(['GET'])
@permission_classes((AllowAny,))
def home_api(request):
    lang = request.GET.get('locale', 'en')
    pairs_data = get_filtered_pairs_24h_stats()
    pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
    btc_usdt_price = pairs_data.get('BTC-USDT', {}).get('price') or 0
    btc_usdt_1fb = 3450
    btc_usdt_percent = round((btc_usdt_price / btc_usdt_1fb * 100) - 100, 0)
    btc_usdt_profit = btc_usdt_price - btc_usdt_1fb
    langs = [l[0] for l in settings.LANGUAGES]

    if lang in langs:
        langs.remove(lang)

    return Response(data={
        'btc_usdt_price': btc_usdt_price,
        'btc_usdt_percent': btc_usdt_percent,
        'btc_usdt_profit': btc_usdt_profit,
        'pairs_data': pairs_data,
        'type_human': random.randrange(0, 3),
        'currency': 'USDT',
    })


@api_view(['GET'])
@permission_classes((AllowAny,))
def coin_item_api_view(request, ticker):
    lang = request.GET.get('locale', 'en')
    langs = [l[0] for l in settings.LANGUAGES]
    if lang not in langs:
        lang = 'en'

    currency_symbols = [i[1].upper() for i in CURRENCIES_LIST]

    if ticker.upper() not in currency_symbols:
        return Response(status=status.HTTP_404_NOT_FOUND)

    coin_static_page = CoinStaticPage.objects.filter(currency=ticker).first()

    coins_info = CoinInfo.get_coins_info()

    if coin_static_page is None or ticker not in coins_info:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if DisabledCoin.is_coin_disabled(ticker.upper()):
        return Response(status=status.HTTP_404_NOT_FOUND)

    pairs_data = get_filtered_pairs_24h_stats()
    pairs_data = {pair['pair']: pair for pair in pairs_data['pairs']}
    coins = {}
    usdt_volume = 0
    for ticker, coin in coins_info.items():
        coin_item = coin
        pair_name = f'{ticker}-USDT'
        if pairs_data.get(pair_name):
            coin_item['price'] = pairs_data[pair_name].get('price') or 0
            coin_item['volume'] = pairs_data[pair_name].get('volume') or 0
            coin_item['price_24h'] = pairs_data[pair_name].get('price_24h') or 0
            usdt_volume += coin_item['volume'] / coin_item['price'] if coin_item['price'] else 0
        coins[ticker] = coin_item

    usdt_item = coins_info['USDT']
    usdt_item['price'] = 1
    usdt_item['volume'] = usdt_volume
    usdt_item['price_24h'] = 0
    coins['USDT'] = usdt_item

    subpages_qs = CoinStaticSubPage.objects.exclude(**{f'slug_{lang}': ''})
    subpages = list(subpages_qs.values(f'slug_{lang}', f'title_{lang}'))
    subpages = [
        {
            'slug': s[f'slug_{lang}'],
            'title': s[f'title_{lang}']
        }
        for s in subpages
    ]

    return Response(data={
        'coins': coins,
        'coin': coins[ticker],
        'ticker': ticker,
        'pairs_data': pairs_data,
        'coin_static_page': CoinStaticPageSerializer(instance=coin_static_page, context={'request': request}).data,
        'has_eur_pair': False,
        'has_rub_pair': False,
        'subpages': subpages,
    })


@api_view(['GET'])
@permission_classes((AllowAny,))
def coin_subpage_api_view(request, ticker, slug):
    lang = request.GET.get('locale', 'en')
    langs = [l[0] for l in settings.LANGUAGES]
    if lang not in langs:
        lang = 'en'

    currency_symbols = [i[1].upper() for i in CURRENCIES_LIST]

    if ticker.upper() not in currency_symbols:
        return Response(status=status.HTTP_404_NOT_FOUND)

    coin_static_sub_page = CoinStaticSubPage.objects.filter(
        **{f'slug_{lang}': slug},
        currency=ticker,
    ).first()

    if coin_static_sub_page is None:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if DisabledCoin.is_coin_disabled(ticker.upper()):
        return Response(status=status.HTTP_404_NOT_FOUND)

    translation.activate(lang)

    data = CoinStaticSubPageSerializer(coin_static_sub_page).data
    return Response(data)
