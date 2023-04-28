from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response

from admin_rest.filters import GenericAllFieldsFilter


class NoDeleteMixin:
    """Prevents destroy"""
    @classmethod
    def has_delete_permission(cls):
        return False

    def destroy(self, request, pk=None):
        response = {'error': 'Delete function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)


class NoUpdateMixin:
    """Prevents update/partial update"""
    @classmethod
    def has_update_permission(cls):
        return False

    def update(self, request, pk=None):
        response = {'error': 'Update function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, pk=None):
        response = {'error': 'Update function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)


class NoCreateMixin:
    """Prevents create"""
    @classmethod
    def has_add_permission(cls):
        return False

    def create(self, request):
        response = {'error': 'Create function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)


class ReadOnlyMixin(NoCreateMixin,
                    NoUpdateMixin,
                    NoDeleteMixin):
    """Only list/retrieve action allowed"""

    def get_readonly_fields(self):
        return self.list_display


class JsonListApiViewMixin(object):
    """
        Displays json field values in list view page
        Uses json_list_fields dict, where the key is JSONField name, the value is some key in json
        """
    json_list_fields = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        all_json_fields = [item for sublist in self.json_list_fields.values() for item in sublist]
        self.list_display += all_json_fields

        for json_field, fields in self.json_list_fields.items():
            for custom_field in fields:
                self._generate_json_field(json_field, custom_field)

    def get_handler_fn(self, json_field_name, fieldname):
        def handler(view, obj):
            res = getattr(obj, json_field_name).get(fieldname)
            # show res as 0.0000000 instead of 0E-8
            if res and res.replace('E-', '').isdigit():
                res = '{:f}'.format(Decimal(res))
            return res

        handler.__name__ = fieldname
        return handler

    def _generate_json_field(self, json_field_name, fieldname):
        handler = self.get_handler_fn(json_field_name, fieldname)
        setattr(self, fieldname, handler)


class NonPaginatedListMixin(object):
    """Removes pagination"""
    filter_backends = (GenericAllFieldsFilter, )
