from django.conf.urls import url
from django.urls import path

from seo.views import (
    PostApiView,
    TagListApiView,
    ContentPhotoApiView,
    PostSlugsApiView,
    coin_item_api_view,
    coin_subpage_api_view,
    home_api,
)

urlpatterns = [
    url(r'blog/$', PostApiView.as_view({'get': 'list'}), name='post-api-list'),
    url(r'blog/(?P<slug>.*)/$',
        PostApiView.as_view({'get': 'retrieve'}),
        name='post-api-list'),
    url(r'tag/$',
        TagListApiView.as_view({'get': 'list'}),
        name='tag-api-list'),
    url(r'contentphoto/$',
        ContentPhotoApiView.as_view({'get': 'list'}), name='contentphoto-api-list'),
    url(r'slugs/$',
        PostSlugsApiView.as_view({'get': 'list'}),
        name='slug-list'),

    path(r'coins/<str:ticker>/', coin_item_api_view),
    path(r'coins/<str:ticker>/<str:slug>/', coin_subpage_api_view),
    path(r'home-page/', home_api),
]
