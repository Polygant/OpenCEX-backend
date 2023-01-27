import base64
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.options import ModelAdmin


class NoTransactionAdmin(admin.ModelAdmin):
    exclude = ('transaction',)


class ReadOnlyMixin:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


class NoDeleteMixIn(object):
    no_delete = True

    def has_add_permission(self, request):
        return False if self.no_delete else True

    def has_delete_permission(self, request, obj=None):
        return False if self.no_delete else True

    def get_actions(self, request):
        actions = super(NoDeleteMixIn, self).get_actions(request)
        if self.no_delete and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class NoAddMixIn:
    no_add = True

    def has_add_permission(self, request):
        return False if self.no_add else True


class ImmutableMixIn(NoDeleteMixIn, NoAddMixIn):
    no_save = True

    def change_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        if self.no_save:
            extra_context['show_save'] = False
            extra_context['show_save_and_continue'] = False
        return super(ImmutableMixIn, self).change_view(request, object_id, extra_context=extra_context)


class JsonListViewMixin(object):
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
        def handler(obj):
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


class JsonListApiViewMixin(JsonListViewMixin):
    def get_handler_fn(self, json_field_name, fieldname):
        def handler(view, obj):
            res = getattr(obj, json_field_name).get(fieldname)
            # show res as 0.0000000 instead of 0E-8
            if res and res.replace('E-', '').isdigit():
                res = '{:f}'.format(Decimal(res))
            return res
        handler.__name__ = fieldname
        return handler


class BaseModelAdmin(NoDeleteMixIn, ModelAdmin):
    show_full_result_count = False

    class Media:
        js = [
            'admin/js/jquery.init.js',
            f'{settings.STATIC_URL}js/menu_filter_collapse.js',
        ]


class SuperUserMixIn(object):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            fields = super(SuperUserMixIn, self).get_readonly_fields(request, obj)
        else:
            fields = [f.name for f in self.model._meta.fields]
        return fields

    def change_view(self, request, object_id, extra_context=None):
        if not request.user.is_superuser:
            extra_context = extra_context or {}
            extra_context['show_save'] = False
            extra_context['show_save_and_continue'] = False
        return super(SuperUserMixIn, self).change_view(request, object_id, extra_context=extra_context)


class MasterPassForm(forms.ModelForm):
    password = forms.CharField(required=True)

    def clean_password(self):
        password = self.cleaned_data['password']
        if password != settings.ADMIN_MASTERPASS:
            raise forms.ValidationError('Invalid password!')
        return password


def download_file_as_base64(filename, content, mimetype):
    return {
        'filename': filename,
        'content': base64.b64encode(content),
        'mimetype': mimetype
    }
