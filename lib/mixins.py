from django.forms.models import model_to_dict
from rest_framework.parsers import JSONParser


class DataSerializer(object):
    def data(self, request):
        return self._get_serializer(request, self.SERIALIZER).validated_data

    @classmethod
    def get_json(cls, request):
        return JSONParser().parse(request)

    @classmethod
    def _get_serializer(cls, request, serializer):
        data = cls.get_json(request)
        serializer = serializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return serializer


class ModelDiffMixin(object):
    """
    A model mixin that tracks model fields' values and provide some useful api
    to know what fields have been changed.
    """
    FIELDS_TO_BE_TRACKED = []

    def __init__(self, *args, **kwargs):
        super(ModelDiffMixin, self).__init__(*args, **kwargs)
        self.__initial = self._dict

    @property
    def diff(self):
        d1 = self.__initial
        d2 = self._dict
        diffs = [(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]]
        if self.FIELDS_TO_BE_TRACKED:
            diffs = [(k, v) for k, v in diffs if k in self.FIELDS_TO_BE_TRACKED]
        return dict(diffs)

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return self.diff.keys()

    def get_field_diff(self, field_name):
        """
        Returns a diff for field if it's changed and None otherwise.
        """
        return self.diff.get(field_name, None)

    def get_tracked_fields_values(self):
        """
        Returns a dict of tracked fields with values.
        """
        return {k: v for k, v in self._dict.items() if k in self.FIELDS_TO_BE_TRACKED}

    def get_changed_fields_values(self):
        return {k: v[1] for k, v in self.diff.items()}

    def save(self, *args, **kwargs):
        """
        Saves model and set initial state.
        """
        super(ModelDiffMixin, self).save(*args, **kwargs)
        self.__initial = self._dict

    @property
    def _dict(self):
        return model_to_dict(self, fields=[field.name for field in
                             self._meta.fields])


class ReadWriteSerializerMixin(object):
    """
    Overrides get_serializer_class to choose the read serializer
    for GET requests and the write serializer for POST requests.

    Set read_serializer_class and write_serializer_class attributes on a
    viewset.
    """

    read_serializer_class = None
    write_serializer_class = None
    update_serializer_class = None
    retrieve_serializer_class = None

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            if self.action in ["update", "partial_update"] and self.update_serializer_class:
                return self.update_serializer_class
            return self.get_write_serializer_class()

        if self.action in ["retrieve"] and self.retrieve_serializer_class:
            return self.retrieve_serializer_class
        return self.get_read_serializer_class()

    def get_read_serializer_class(self):
        assert self.read_serializer_class is not None, (
            "'%s' should either include a `read_serializer_class` attribute,"
            "or override the `get_read_serializer_class()` method."
            % self.__class__.__name__
        )
        return self.read_serializer_class

    def get_write_serializer_class(self):
        assert self.write_serializer_class is not None, (
            "'%s' should either include a `write_serializer_class` attribute,"
            "or override the `get_write_serializer_class()` method."
            % self.__class__.__name__
        )
        return self.write_serializer_class
