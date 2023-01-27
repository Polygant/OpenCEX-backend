from django.conf import settings
from rest_framework import serializers

from core.currency import CurrencySerialField
from core.serializers import TranslateModelSerializer
from lib.fields import JSDatetimeField
from seo.models import Post, Tag, ContentPhoto, CoinStaticPage, CoinStaticSubPage


class TagSerializer(TranslateModelSerializer):
    title = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()

    def _translate(self, obj, value):
        request = self.context['request']
        locale = request.GET.get('locale')
        if locale and locale in dict(settings.LANGUAGES):
            return getattr(obj, value + '_' + locale)
        return getattr(obj, value)

    def get_title(self, obj):
        return self._translate(obj, 'title')

    def get_name(self, obj):
        return self._translate(obj, 'name')

    def get_meta_title(self, obj):
        return self._translate(obj, 'meta_title')

    def get_meta_description(self, obj):
        return self._translate(obj, 'meta_description')

    class Meta:
        model = Tag
        fields = (
            'id', 'slug', 'name', 'title', 'meta_title', 'meta_description',
        )


class PostSerializer(TranslateModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    title = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()
    slugs = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()

    created = JSDatetimeField(required=False)

    def get_title(self, obj):
        return self._translate(obj, 'title')

    def get_text(self, obj):
        return self._translate(obj, 'text')

    def get_slug(self, obj):
        return self._translate(obj, 'slug')

    def get_slugs(self, obj):
        return [obj.slug_ru, obj.slug_en]

    def get_meta_title(self, obj):
        return self._translate(obj, 'meta_title')

    def get_meta_description(self, obj):
        return self._translate(obj, 'meta_description')

    class Meta:
        model = Post
        fields = (
            'slug', 'slugs', 'title', 'text', 'preview_image', 'views_count',
            'meta_title', 'meta_description', 'tags', 'created',
        )
        depth = 1


class ContentPhotoSerializer(TranslateModelSerializer):
    title = serializers.SerializerMethodField()

    def get_title(self, obj):
        return self._translate(obj, 'title')

    class Meta:
        model = ContentPhoto
        fields = ('title', 'announce_image')
        depth = 1


class CoinStaticPageSerializer(TranslateModelSerializer):
    currency = CurrencySerialField()
    title = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    trade_button_text = serializers.SerializerMethodField()
    header_text = serializers.SerializerMethodField()
    usd_block_text = serializers.SerializerMethodField()
    eur_block_text = serializers.SerializerMethodField()
    rub_block_text = serializers.SerializerMethodField()
    footer_text = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()

    def get_title(self, obj):
        return self._translate(obj, 'title')

    def get_name(self, obj):
        return self._translate(obj, 'name')

    def get_trade_button_text(self, obj):
        return self._translate(obj, 'trade_button_text')

    def get_header_text(self, obj):
        return self._translate(obj, 'header_text')

    def get_usd_block_text(self, obj):
        return self._translate(obj, 'usd_block_text')

    def get_eur_block_text(self, obj):
        return self._translate(obj, 'eur_block_text')

    def get_rub_block_text(self, obj):
        return self._translate(obj, 'rub_block_text')

    def get_footer_text(self, obj):
        return self._translate(obj, 'footer_text')

    def get_meta_description(self, obj):
        return self._translate(obj, 'meta_description')

    class Meta:
        model = CoinStaticPage
        fields = (
            'currency',
            'title',
            'name',
            'trade_button_text',
            'header_text',
            'usd_block_text',
            'eur_block_text',
            'rub_block_text',
            'footer_text',
            'meta_description'
        )


class CoinStaticSubPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinStaticSubPage
        fields = ('currency', 'slug', 'title', 'content', 'meta_title', 'meta_description',)
