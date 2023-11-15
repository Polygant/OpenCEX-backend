import json
from collections import OrderedDict
from functools import wraps

from django.conf import settings
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth import get_permission_codename
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.base import ModelBase
from django.db.models.fields import NOT_PROVIDED
from django.forms import model_to_dict
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe
from rest_framework import filters
from rest_framework import serializers
from rest_framework import viewsets, status
from rest_framework.decorators import action as base_action
from rest_framework.fields import ImageField
from rest_framework.fields import SkipField
from rest_framework.metadata import SimpleMetadata
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.relations import PrimaryKeyRelatedField, PKOnlyObject, ManyRelatedField
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.serializers import ModelSerializer
from rest_framework.serializers import SerializerMethodField

from admin_rest.fields import CurrencySerialRestField
from admin_rest.fields import ForeignSerialField
from admin_rest.filters import GenericAllFieldsFilter
from admin_rest.utils import get_user_permissions
from core.currency import CurrencyModelField
from core.models.inouts.pair import PairModelField, PairSerialRestField
from lib.fields import JSDatetimeField, RichTextField, RichTextSerialField, ImageSerialField, TextSerialField, \
    JsonSerialField, SVGAndImageField

User = get_user_model()


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class ImproperlyConfigured(Exception):
    pass


class AuthPermissionViewSetMixin:
    NOT_FOUND_PERMISSION_DEFAULT = False
    permission_map = dict()

    def get_permission_map(self):
        permission_map = {
            'list': self._make_permission_key('view'),
            'retrieve': self._make_permission_key('view'),
            'create': self._make_permission_key('add'),
            'update': self._make_permission_key('change'),
            'partial_update': self._make_permission_key('change'),
            'destroy': self._make_permission_key('delete'),
        }
        permission_map.update(self.permission_map)
        return permission_map

    @cached_property
    def _options(self):
        return self.queryset.model._meta

    def _make_permission_key(self, action):
        code_name = get_permission_codename(action, self._options)
        return "{0}.{1}".format(self._options.app_label, code_name)

    def has_perm_action(self, action, request, obj=None):
        if not action:
            return False

        if action == 'metadata':
            return True

        perm_map = self.get_permission_map()
        if hasattr(getattr(self, action), 'permissions'):
            perm_map.update(**{action: getattr(self, action).permissions})

        if action not in perm_map:
            return self.NOT_FOUND_PERMISSION_DEFAULT

        perm_code = perm_map[action]
        if callable(perm_code):
            return perm_code(self, action, request, obj)
        if isinstance(perm_code, bool):
            return perm_code

        if perm_code in ['view', 'add', 'change', 'delete']:
            perm_code = self._make_permission_key(perm_code)

        # checks list of permissions
        if isinstance(perm_code, list) or isinstance(perm_code, tuple):
            for code in perm_code:
                if code in ['view', 'add', 'change', 'delete']:
                    code = self._make_permission_key(code)
                has_perm = request.user.has_perm(code)
                if has_perm:
                    return has_perm
            return False

        return request.user.has_perm(perm_code)


class IsStaffAccess(BasePermission):
    """
    Allows access only to authenticated Trainee users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

    def has_object_permission(self, request, view, obj):
        """
        Return `True` if permission is granted, `False` otherwise.
        """
        return self.has_permission(request, view)


class HasPermissionAccess(BasePermission):
    """
    Allows access only to authenticated Trainee users.
    """

    def has_permission(self, request, view):
        assert hasattr(view, 'get_permission_map'), """
        Must be inherit from RestFulModelAdmin to use this permission
        """
        return view.has_perm_action(view.action, request)

    def has_object_permission(self, request, view, obj):
        """
        Return `True` if permission is granted, `False` otherwise.
        """
        return view.has_perm_action(view.action, request, obj)


class ModelDiffHelper(object):
    def __init__(self, initial):
        self.__initial = self._dict(initial)
        self._new_object = None

    def set_changed_model(self, new_object):
        data = self._dict(new_object)
        if self._new_object is not None:
            self.__initial = data
        self._new_object = data
        return self

    @property
    def diff(self):
        if not self._new_object:
            return {}
        d1 = self.__initial
        d2 = self._new_object
        diffs = [(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]]
        return dict(diffs)

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return list(self.diff.keys())

    def get_field_diff(self, field_name):
        """
        Returns a diff for field if it's changed and None otherwise.
        """
        return self.diff.get(field_name, None)

    def _dict(self, model):
        return model_to_dict(model, fields=[field.name for field in
                                            model._meta.fields])


class CustomMetadata(SimpleMetadata):
    label_lookup = SimpleMetadata.label_lookup

    def __init__(self, *args, **kwargs):
        super(CustomMetadata, self).__init__(*args, **kwargs)
        # TODO make consts for out fields
        self.label_lookup[JSDatetimeField] = 'datetime'
        self.label_lookup[PrimaryKeyRelatedField] = 'foreign'
        self.label_lookup[ManyRelatedField] = 'foreign'
        self.label_lookup[SerializerMethodField] = 'string'
        self.label_lookup[CurrencySerialRestField] = 'choice'
        self.label_lookup[PairSerialRestField] = 'choice'
        self.label_lookup[ImageField] = 'image-upload'
        self.label_lookup[ImageSerialField] = 'image-upload'
        self.label_lookup[RichTextSerialField] = 'rich-text'
        self.label_lookup[TextSerialField] = 'text'
        self.label_lookup[JsonSerialField] = 'json'
        self.label_lookup[ForeignSerialField] = 'foreign'

    def determine_metadata(self, request, view):
        metadata = OrderedDict()
        # view name
        metadata['name'] = view.get_view_name()
        # view detail page fields
        metadata['fields'] = []
        # view list page fields
        metadata['list_fields'] = []
        # actions with queryset
        metadata['actions'] = []
        # global actions. Queryset not used
        metadata['global_actions'] = []
        # ref models in detail page of entry
        metadata['inline_forms'] = []

        metadata['filters'] = []

        metadata['search_enabled'] = False

        if hasattr(view, 'get_single_serializer'):
            serializer = view.get_single_serializer()
            fields = self.get_serializer_info(serializer)
            metadata['fields'] = fields

        if hasattr(view, 'get_serializer'):
            serializer = view.get_serializer()
            fields = self.get_serializer_info(serializer)
            metadata['list_fields'] = fields

        if hasattr(view, 'actions'):
            actions = self.get_actions(view, view.actions)
            metadata['actions'] = actions

        if hasattr(view, 'global_actions'):
            actions = self.get_actions(view, view.global_actions)
            metadata['global_actions'] = actions

        if hasattr(view, 'inline_forms'):
            inlines = self.get_inline_forms(view, view.inline_forms)
            metadata['inline_forms'] = inlines

        if getattr(view, 'search_fields', None):
            metadata['search_enabled'] = True

        if getattr(view, 'filterset_fields', None):
            serializer = view.get_all_fields_serializer()
            fields = self.get_serializer_info(serializer)
            metadata['filters'] = {k: v for k, v in fields.items() if v['filterable']}

        return metadata

    def get_inline_forms(self, view, inlines):
        res = []
        for inline, filter_by in inlines:
            if isinstance(filter_by, str):
                filter_by = {filter_by: 'id'}
            if isinstance(filter_by, list):
                filter_by = {v: 'id' for v in filter_by}
            res.append({
                'resource': site.get_resource_name_by_view_class(inline),
                'filter_by': filter_by,
                'fields': inline.list_display
            })
        return res

    def get_actions(self, view, view_actions):
        actions = []
        for action_name in view_actions:
            if not view.has_perm_action(action_name, view.request):
                continue

            action_fn = getattr(view, action_name, None)
            if action_fn:
                info = {
                    'url': view.reverse_action(action_name.replace('_', '-')),
                    'name': getattr(action_fn, 'short_description', action_fn.__name__),
                    'fields': [],
                }

                if isinstance(view_actions, dict):
                    fields = []
                    for field in view_actions[action_name]:
                        if isinstance(field, str):
                            field = {
                                'name': field,
                                'label': field.capitalize(),
                            }

                        # default text type
                        if 'type' not in field:
                            field['type'] = 'text'
                        fields.append(field)
                    info['fields'] = fields

                actions.append(info)

        return actions

    def get_field_attributes(self, serializer_field, model_field):
        attributes = OrderedDict()

        default = getattr(model_field, 'default', NOT_PROVIDED)
        is_nullable = getattr(model_field, 'null', None)
        is_read_only = getattr(serializer_field, 'read_only', None)
        # attributes['required'] = (default is NOT_PROVIDED) and not is_nullable and is_read_only

        attributes['required'] = getattr(serializer_field, 'required', False)
        attributes['nullable'] = getattr(model_field, 'null', False)

        attrs_dict = {
            'read_only': 'read_only',
            'label': 'label',
            'help_text': 'hint',
            'min_length': 'min_length',
            'max_length': 'max_length',
            'min_value': 'min',
            'max_value': 'max',
        }

        for attr, front_attr in attrs_dict.items():
            value = getattr(serializer_field, attr, None)
            if value is not None and value != '':
                attributes[front_attr] = force_str(value, strings_only=True)

        if getattr(serializer_field, 'child', None):
            attributes['child'] = self.get_field_info(serializer_field.child)
        elif getattr(serializer_field, 'fields', None):
            attributes['children'] = self.get_serializer_info(serializer_field)

        if not isinstance(serializer_field, (serializers.RelatedField, serializers.ManyRelatedField)):
            if hasattr(serializer_field, 'choices'):
                attributes['choices'] = []
                if is_nullable:
                    attributes['choices'].append({'value': None, 'text': '<empty>'})
                attributes['choices'].extend([
                    {
                        'value': choice_value,
                        'text': force_str(choice_name, strings_only=True)
                    }
                    for choice_value, choice_name in serializer_field.choices.items()
                ])

        if self.label_lookup[serializer_field] == 'foreign':
            if isinstance(serializer_field, ManyRelatedField):
                model = serializer_field.child_relation.queryset.model
                attributes['multiple'] = True
            else:
                model = model_field.related_model
            attributes['reference'] = f'{site.get_resource_name(model)}'
        return attributes

    def get_field_info(self, field):
        """
        Given an instance of a serializer field, return a dictionary
        of metadata about it.
        """
        view = field.context['view']
        model_fields = {f.name: f for f in view._options.fields}
        model_field = model_fields.get(field.field_name)

        sortable_fields = getattr(view, 'ordering_fields', '__all__')
        filterable_fields = getattr(view, 'filterset_fields', None)

        field_info = OrderedDict()
        field_info['type'] = self.label_lookup[field]
        field_info['source'] = field.field_name
        field_info['sortable'] = False
        field_info['filterable'] = False

        field_info['default'] = self.get_field_default_value(model_field)

        if sortable_fields == '__all__' or (isinstance(sortable_fields, list) and field.field_name in sortable_fields):
            field_info['sortable'] = True

        if (isinstance(filterable_fields, list) or isinstance(filterable_fields, tuple)) \
                and field.field_name in filterable_fields:
            field_info['filterable'] = True

        field_info['attributes'] = self.get_field_attributes(field, model_field)
        field_info['attributes']['searchable'] = field.field_name in (
                view.vue_resource_extras.get('searchable_fields') or [])

        return field_info

    def get_field_default_value(self, model_field):
        default = getattr(model_field, 'default', None)
        if default is NOT_PROVIDED:
            default = None
        elif callable(default):
            default = default()

        if isinstance(model_field, JSONField) or isinstance(model_field, models.JSONField):
            default = json.dumps(default, indent=2)
        return default


class RestFulModelAdmin(AuthPermissionViewSetMixin, viewsets.ModelViewSet):
    queryset = None
    single_serializer_class = None
    permission_classes = (IsStaffAccess, HasPermissionAccess)
    list_display = '__all__'
    fields = '__all__'
    readonly_fields = []
    ordering_fields = '__all__'
    filterset_fields = []
    search_fields = []
    metadata_class = CustomMetadata
    filter_backends = (GenericAllFieldsFilter, filters.OrderingFilter, filters.SearchFilter)
    vue_resource_extras: dict = {}
    inline_forms: []  # detail page entities

    def __init__(self, *args, **kwargs):
        super(RestFulModelAdmin, self).__init__(*args, **kwargs)
        filterset_fields = set(self.filterset_fields)
        filterset_fields.add('id')

        for field in self._options.fields:
            if type(field) in [models.OneToOneField, models.ForeignKey, models.ManyToManyField]:
                filterset_fields.add(field.name + '_id')

        self.filterset_fields = tuple(filterset_fields)

    def get_readonly_fields(self):
        return self.readonly_fields

    @classmethod
    def has_add_permission(cls):
        return True

    @classmethod
    def has_update_permission(cls):
        return True

    @classmethod
    def has_delete_permission(cls):
        return True

    @classmethod
    def get_view_permissions(cls):
        res = ['show', 'list']
        if cls.has_add_permission():
            res.append('create')
        if cls.has_update_permission():
            res.append('edit')
        if cls.has_delete_permission():
            res.append('delete')
        return res

    @staticmethod
    def get_doc():
        return 'asd'

    def get_urls(self):
        return []

    def get_permission_map(self):
        permission_map = {
            'list': self._make_permission_key('view'),
            'retrieve': self._make_permission_key('view'),
            'create': self._make_permission_key('add'),
            'update': self._make_permission_key('change'),
            'partial_update': self._make_permission_key('change'),
            'destroy': self._make_permission_key('delete'),
        }
        permission_map.update(self.permission_map)
        return permission_map

    def log_addition(self, request, object, message):
        """
        Log that an object has been successfully added.

        The default implementation creates an admin LogEntry object.
        """
        from django.contrib.admin.models import LogEntry, ADDITION
        return LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=ADDITION,
            change_message=message,
        )

    def log_change(self, request, object, message):
        """
        Log that an object has been successfully changed.

        The default implementation creates an admin LogEntry object.
        """
        from django.contrib.admin.models import LogEntry, CHANGE
        return LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=CHANGE,
            change_message=message,
        )

    def log_deletion(self, request, object, object_repr):
        """
        Log that an object will be deleted. Note that this method must be
        called before the deletion.

        The default implementation creates an admin LogEntry object.
        """
        from django.contrib.admin.models import LogEntry, DELETION
        return LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(object).pk,
            object_id=object.pk,
            object_repr=object_repr,
            action_flag=DELETION,
        )

    def get_single_serializer_class(self):
        return self.single_serializer_class if self.single_serializer_class else self.get_serializer_class(True)

    def get_all_fields_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class(all_fields=True)
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_single_serializer(self, *args, **kwargs):
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = self.get_single_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_serializer_representation_fn(self, cls):
        """Custom fields representation fn"""

        def validate_fn(sf, instance):
            """
            Object instance -> Dict of primitive datatypes.
            """
            ret = OrderedDict()
            fields = sf._readable_fields

            for field in fields:
                try:
                    attribute = field.get_attribute(instance)
                except SkipField:
                    continue

                # We skip `to_representation` for `None` values so that fields do
                # not have to explicitly deal with that case.
                #
                # For related fields with `use_pk_only_optimization` we need to
                # resolve the pk value.
                check_for_none = attribute.pk if isinstance(attribute, PKOnlyObject) else attribute
                if check_for_none is None:
                    ret[field.field_name] = None
                else:
                    repr = field.to_representation(attribute)
                    if isinstance(field, JsonSerialField) or isinstance(field, RichTextSerialField):
                        repr = mark_safe(repr)
                    if isinstance(repr, str) and not isinstance(repr, SafeString):
                        repr = escape(repr)
                    ret[field.field_name] = repr
            return ret

        return validate_fn

    def get_serializer_class(self, single=False, all_fields=False):
        serializer_class = super().get_serializer_class()

        view_fields = self.fields if single else self.list_display
        if isinstance(view_fields, tuple):
            view_fields = list(view_fields)

        if not view_fields or view_fields == '__all__' or all_fields:
            serializer_class_fields = list([f.name for f in serializer_class.Meta.model._meta.fields])
        else:
            if 'id' not in view_fields:
                view_fields = ['id'] + view_fields
            serializer_class_fields = view_fields

        serializer_class_fields += ['_label']  # default object representation

        # redefine serializer fields
        serializer_class._declared_fields = {}
        for field_name in serializer_class_fields:
            if callable(getattr(self, field_name, None)):
                # add SerializerMethodField and its method to serializer
                field_method = getattr(self, field_name)
                # if custom field type defined
                if hasattr(field_method, 'serial_class'):
                    serializer_class._declared_fields[field_name] = field_method.serial_class()
                else:
                    serializer_class._declared_fields[field_name] = SerializerMethodField()
                    setattr(serializer_class, f'get_{field_name}', field_method)
            if field_name == '_label':
                serializer_class._declared_fields[field_name] = SerializerMethodField()
                setattr(serializer_class, f'get_{field_name}', lambda self_cls, obj: str(obj))

        # setup readonly fields
        readonly_fields = self.get_readonly_fields()
        if isinstance(readonly_fields, list) or isinstance(readonly_fields, tuple):
            serializer_class.Meta.read_only_fields = readonly_fields

        # search original classes for translated fields and delete original field
        translated_fields_classes = {}
        to_remove_original_translated_fields = set()
        serializer_fields_classes = {f.name: f.__class__ for f in serializer_class.Meta.model._meta.fields}
        for model_field in serializer_class.Meta.model._meta.fields:
            if model_field.__class__.__name__.startswith('Translation'):
                original_field_name = model_field.name.rsplit('_', 1)[0]
                to_remove_original_translated_fields.add(original_field_name)
                if original_field_name in serializer_fields_classes:
                    translated_fields_classes[model_field.name] = serializer_fields_classes[original_field_name]
                else:
                    to_remove_original_translated_fields.add(model_field.name)

        serializer_class_fields = [f for f in serializer_class_fields
                                   if f not in to_remove_original_translated_fields]

        # custom fields
        for model_field in serializer_class.Meta.model._meta.fields:
            if model_field.name not in serializer_class_fields:
                # skip missing fields
                continue

            CustomField = None
            field_args = {}

            field_type = type(model_field)

            # handle translated fields
            if model_field.name in translated_fields_classes:
                field_type = translated_fields_classes[model_field.name]

            if isinstance(model_field, models.DateTimeField):
                CustomField = JSDatetimeField
            elif field_type == PairModelField:
                CustomField = PairSerialRestField
            elif isinstance(model_field, models.ForeignKey) and not single:
                CustomField = ForeignSerialField
            elif field_type == CurrencyModelField:
                CustomField = CurrencySerialRestField
            elif field_type == RichTextField:
                CustomField = RichTextSerialField
            elif field_type == models.TextField:
                CustomField = TextSerialField
            elif field_type in [models.ImageField, SVGAndImageField, ImageSerialField]:
                CustomField = ImageSerialField
            elif field_type in [JSONField, models.JSONField]:
                CustomField = JsonSerialField

            if CustomField:
                is_read_only = model_field.name in readonly_fields \
                               or getattr(model_field, 'auto_now', False) \
                               or getattr(model_field, 'auto_now_add', False)
                default = getattr(model_field, 'default', NOT_PROVIDED)
                is_nullable = getattr(model_field, 'null', None)
                if CustomField != ForeignSerialField:
                    field_args['required'] = (default is NOT_PROVIDED) and not is_nullable and not is_read_only

                field_args['read_only'] = is_read_only
                field_args['allow_null'] = model_field.null
                if CustomField in [TextSerialField, RichTextSerialField]:
                    field_args['allow_blank'] = model_field.blank
                serializer_class._declared_fields[model_field.name] = CustomField(**field_args)

        serializer_class.Meta.fields = serializer_class_fields
        setattr(serializer_class, 'to_representation', self.get_serializer_representation_fn(serializer_class))
        return serializer_class

    def list(self, request, *args, **kwargs):
        """list all of objects"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, **kwargs):
        """Create new object"""
        serializer = self.get_single_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        self.log_addition(request, serializer.instance, [{'added': {
            'name': str(serializer.instance._meta.verbose_name),
            'object': str(serializer.instance),
        }}])
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def retrieve(self, request, pk=None, **kwargs):
        """Get object Details"""
        instance = self.get_object()
        serializer = self.get_single_serializer(instance)
        return Response(serializer.data)

    def update(self, request, pk=None, **kwargs):
        """Update object"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_single_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        helper = ModelDiffHelper(instance)
        self.perform_update(serializer)

        self.log_change(
            request,
            serializer.instance,
            [{'changed': {
                'name': str(serializer.instance._meta.verbose_name),
                'object': str(serializer.instance),
                'fields': helper.set_changed_model(serializer.instance).changed_fields
            }}]
        )

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def partial_update(self, request, pk=None, **kwargs):
        """Partial Update"""
        return super().partial_update(request, pk=pk, **kwargs)

    def destroy(self, request, pk=None, **kwargs):
        """Delete object"""
        instance = self.get_object()
        self.log_deletion(request, instance, [{
            'deleted': {
                'name': str(instance._meta.verbose_name),
                'object': str(instance),
            }
        }])
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RestFulAdminSite:
    def __init__(self, view_class=RestFulModelAdmin):
        self._registry = {}
        self._model_by_view_registry = {}
        self._url_patterns = []
        self.default_view_class = view_class

    def get_registered_models(self):
        res = []
        for model in self._registry:
            res.append(self.get_model_url(model))
        return sorted(res)

    def get_resource_name_by_view_class(self, view_class):
        inv_map = {v: k for k, v in self._registry.items()}
        model = inv_map.get(view_class)
        if model:
            return self.get_resource_name(model)
        model = self._model_by_view_registry.get(view_class)
        if model:
            return self.get_resource_name(model)

    def get_resources(self):
        res = []
        for model, view in self._registry.items():
            # https://www.okami101.io/vuetify-admin/guide/resources.html#resource-object-structure
            data = {
                'name': self.get_resource_name(model),
                'actions': view.get_view_permissions(),
                'api': f'/{self.get_model_url(model)}/',
                'aside': False,
            }
            if view.vue_resource_extras:
                data.update(view.vue_resource_extras)

            res.append(data)
        return res

    def make_navigation(self, user):
        all_permissions = get_user_permissions(user)
        is_admin = 'admin' in all_permissions
        menu = settings.VUE_ADMIN_SIDE_MENU

        new_menu = []

        for entry in menu:
            model = entry.get('model')
            if not model:
                new_menu.append(entry)
            else:
                app_label, model_name = model.split('.')
                # todo check model existence
                view_perm_name = f'{app_label}_{model_name}_view'
                if is_admin or view_perm_name in all_permissions:
                    new_menu.append({
                        'icon': entry.get('icon'),
                        'link': {'name': f'{app_label}_{model_name}_list'},
                        'text': entry.get('text') or (f'{app_label.capitalize()} {model_name.capitalize()}')
                    })
        return new_menu

    def register_decorator(self, *model_or_iterable, **options):
        def wrapper(view_class):
            self.register(model_or_iterable, view_class, **options)
            return view_class

        return wrapper

    def register(self, model_or_iterable, view_class=None, **options):
        if not view_class:
            view_class = self.default_view_class

        if isinstance(model_or_iterable, ModelBase):
            model_or_iterable = [model_or_iterable]
        for model in model_or_iterable:
            if model._meta.abstract:
                raise ImproperlyConfigured(
                    'The model %s is abstract, so it cannot be registered with admin.' % model.__name__
                )

            if model in self._registry:
                raise AlreadyRegistered('The model %s is already registered' % model.__name__)
            options.update({
                "__doc__": self.generate_docs(model)
            })
            self._model_by_view_registry[view_class] = model
            view_class = type("%sAdmin" % model.__name__, (view_class,), options)
            # self.set_docs(view_class, model)
            # Instantiate the admin class to save in the registry
            self._registry[model] = view_class

    def register_url_pattern(self, url_pattern):
        self._url_patterns.append(url_pattern)

    @classmethod
    def generate_docs(cls, model):
        return """
    ### The APIs include:


    > `GET`  {app}/{model} ===> list all `{verbose_name_plural}` page by page;

    > `POST`  {app}/{model} ===> create a new `{verbose_name}`

    > `GET` {app}/{model}/123 ===> return the details of the `{verbose_name}` 123

    > `PATCH` {app}/{model}/123 and `PUT` {app}/{model}/123 ==> update the `{verbose_name}` 123

    > `DELETE` {app}/{model}/123 ===> delete the `{verbose_name}` 123

    > `OPTIONS` {app}/{model} ===> show the supported verbs regarding endpoint `{app}/{model}`

    > `OPTIONS` {app}/{model}/123 ===> show the supported verbs regarding endpoint `{app}/{model}/123`

            """.format(
            app=model._meta.app_label,
            model=model._meta.model_name,
            verbose_name=model._meta.verbose_name,
            verbose_name_plural=model._meta.verbose_name_plural
        )

    def unregister(self, model_or_iterable):
        """
        Unregister the given model(s).

        If a model isn't already registered, raise NotRegistered.
        """
        if isinstance(model_or_iterable, ModelBase):
            model_or_iterable = [model_or_iterable]
        for model in model_or_iterable:
            if model not in self._registry:
                raise NotRegistered('The model %s is not registered' % model.__name__)
            del self._registry[model]

    def is_registered(self, model):
        """
        Check if a model class is registered with this `AdminSite`.
        """
        return model in self._registry

    def get_model_basename(self, model):
        return None

    def get_model_url(self, model):
        return '%s/%s' % (model._meta.app_label, model._meta.model_name)

    def get_resource_name(self, model):
        return f'{model._meta.app_label}_{model._meta.model_name}'

    def get_urls(self):
        router = DefaultRouter()
        view_sets = []
        for model, view_set in self._registry.items():
            if view_set.queryset is None:
                view_set.queryset = model.objects.all()
            #  Creates default serializer
            if view_set.serializer_class is None:
                serializer_class = type("%sModelSerializer" % model.__name__, (ModelSerializer,), {
                    "Meta": type("Meta", (object,), {
                        "model": model,
                        "fields": "__all__"
                    }),
                })
                view_set.serializer_class = serializer_class

            view_sets.append(view_set)
            router.register(self.get_model_url(model), view_set, self.get_model_basename(model))

        return router.urls + self._url_patterns

    @property
    def urls(self):
        return self.get_urls()


site = RestFulAdminSite()


def register(*model_or_iterable, **options):
    return site.register_decorator(*model_or_iterable, **options)


def action(permissions=None, methods=['POST'], detail=False, url_path=None, url_name=None, custom_response=False,
           **kwargs):
    def decorator(func):
        base_func = base_action(methods, detail, url_path, url_name, **kwargs)(func)
        base_func.permissions = permissions

        @wraps(base_func)
        def wrapper(base_admin_class, request, *args, **kwargs):
            ids = request.data.get('ids')

            Model = base_admin_class.serializer_class.Meta.model
            queryset = Model.objects.filter(id__in=ids) if ids else Model.objects.none()

            res = base_func(base_admin_class, request, queryset, *args, **kwargs)
            if queryset:
                for entry in queryset:
                    LogEntry.objects.log_action(
                        user_id=request.user.pk,
                        content_type_id=get_content_type_for_model(entry).pk,
                        object_id=entry.pk,
                        object_repr=str(entry),
                        action_flag=CHANGE,
                        change_message=[{'action': {
                            'name': f'{base_admin_class.__class__.__name__} {base_func.__name__}',
                            'object': str(entry),
                        }}],
                    )
            else:
                LogEntry.objects.log_action(
                    user_id=request.user.pk,
                    content_type_id=None,
                    object_id=None,
                    object_repr='',
                    action_flag=CHANGE,
                    change_message=[{'action': {
                        'name': f'{base_admin_class.__class__.__name__} {base_func.__name__}',
                    }}],
                )

            if custom_response:
                return res

            if res is None:
                return Response(status=status.HTTP_200_OK)
            return Response(res, status=status.HTTP_200_OK)

        return wrapper

    return decorator


class DefaultApiAdmin(RestFulModelAdmin):
    ordering = ('-id',)
    # permission_classes = (AllowAny, )
    # filter_backends = [GenericAllFieldsFilter, filters.OrderingFilter, filters.SearchFilter]
