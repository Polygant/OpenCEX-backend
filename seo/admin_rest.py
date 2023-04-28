from django.utils.safestring import mark_safe

from admin_rest import restful_admin as api_admin
from admin_rest.restful_admin import DefaultApiAdmin
from lib.utils import get_domain
from seo.models import (
    Post,
    Tag,
    ContentPhoto,
    CoinStaticPage,
    CoinStaticSubPage,
)


@api_admin.register(ContentPhoto)
class ContentPhotoAdmin(DefaultApiAdmin):
    vue_resource_extras = {'data_table': {'rowClick': 'edit'}}
    list_display = ['title_ru', 'title_en', 'announce_image', 'link']
    search_fields = ['title_ru', 'title_en']

    def link(self, obj):
        link = f'https://{get_domain()}{obj.announce_image.url}'
        return mark_safe(f'<a href="{link}">{link}</a>')


@api_admin.register(Post)
class PostAdmin(DefaultApiAdmin):
    vue_resource_extras = {'data_table': {'rowClick': 'edit'}}
    fields = ['created', 'preview_image', 'tags',
              'slug_ru', 'title_ru', 'text_ru', 'meta_title_ru', 'meta_description_ru',
              'slug_en', 'title_en', 'text_en', 'meta_title_en', 'meta_description_en',
              'views_count',]

    list_display = ['created', 'preview_image', 'slug_ru', 'title_ru', 'views_count']
    search_fields = ['slug_ru', 'slug_en', 'title_ru', 'title_en', 'tags']


@api_admin.register(Tag)
class TagAdmin(DefaultApiAdmin):
    vue_resource_extras = {'data_table': {'rowClick': 'edit'}}
    fields = ['slug', 'name_ru', 'title_ru', 'meta_title_ru', 'meta_description_ru',
                    'name_en', 'title_en', 'meta_title_en', 'meta_description_en']
    list_display = ['slug', 'name_ru', 'title_ru']
    search_fields = ['slug', 'name_ru', 'title_ru', 'name_en', 'title_en']


@api_admin.register(CoinStaticPage)
class CoinStaticPageApiAdmin(DefaultApiAdmin):
    pass


@api_admin.register(CoinStaticSubPage)
class CoinStaticSubPageAdmin(DefaultApiAdmin):
    fields = ('currency', 'slug_ru', 'slug_en', 'title_ru', 'title_en', 'content_ru', 'content_en',
              'meta_title_ru', 'meta_title_en', 'meta_description_ru', 'meta_description_en')
    list_display = ('currency', 'slug_ru', 'slug_en', 'title_ru', 'title_en')
    filterset_fields = ('currency', )