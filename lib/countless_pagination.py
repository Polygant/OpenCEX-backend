from django.core.paginator import Paginator
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.utils.urls import replace_query_param


class CountLessPaginator(LimitOffsetPagination):
    def paginate_queryset(self, queryset, request, view=None):
        self.count = None
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.offset = self.get_offset(request)
        self.request = request
        if self.template is not None:
            self.display_page_controls = True

        return list(queryset[self.offset:self.offset + self.limit])

    def get_next_link(self):
        url = self.request.build_absolute_uri()
        url = replace_query_param(url, self.limit_query_param, self.limit)

        offset = self.offset + self.limit
        return replace_query_param(url, self.offset_query_param, offset)


class CountLessPaginatorAdmin(Paginator):
    @property
    def count(self):
        return 100000
