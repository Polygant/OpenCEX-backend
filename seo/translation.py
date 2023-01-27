from modeltranslation.translator import translator, TranslationOptions

from seo.models import CoinStaticPage
from seo.models import CoinStaticSubPage
from seo.models import ContentPhoto
from seo.models import Post
from seo.models import Tag


class CoinStaticPageTranslationOptions(TranslationOptions):
    fields = (
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


class CoinStaticSubPageTranslationOptions(TranslationOptions):
    fields = (
        'slug',
        'title',
        'content',
        'meta_title',
        'meta_description',
    )


class PostTranslationOptions(TranslationOptions):
    fields = (
        'title',
        'text',
        'slug',
        'meta_title',
        'meta_description'
    )


class TagTranslationOptions(TranslationOptions):
    fields = (
        'name',
        'title',
        'meta_title',
        'meta_description'
    )
    required_languages = {'ru': ('title',)}


class ContentPhotoTranslationOptions(TranslationOptions):
    fields = ('title',)


translator.register(Post, PostTranslationOptions)
translator.register(Tag, TagTranslationOptions)
translator.register(ContentPhoto, ContentPhotoTranslationOptions)
translator.register(CoinStaticPage, CoinStaticPageTranslationOptions)
translator.register(CoinStaticSubPage, CoinStaticSubPageTranslationOptions)
