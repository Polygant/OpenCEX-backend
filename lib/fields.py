import base64
import contextlib
import datetime
import json
import time
import xml.etree.cElementTree as et
from io import BytesIO

from django import forms
from django.core.exceptions import ValidationError
from django.core.files import File as DjangoFile
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import FileExtensionValidator, get_available_image_extensions
from django.db import models
from django.db.models import JSONField
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.fields import Field, FileField


class JSDatetimeField(Field):
    def to_representation(self, obj):
        if isinstance(obj, datetime.datetime):
            return int(obj.timestamp() * 1000)
        elif isinstance(obj, (int, float)):
            return obj if obj >= 10**11 else obj * 1000
        raise ValueError(obj)

    def to_internal_value(self, value):
        value = int(value)
        if value >= 10**11:
            value = value / 1000
        return datetime.datetime.fromtimestamp(value)


class MoneyField(models.DecimalField):
    """
    Default init values overriden
    """

    def __init__(self, verbose_name=None, name=None, max_digits=32, decimal_places=8, **kwargs):
        super().__init__(verbose_name, name, max_digits, decimal_places, **kwargs)


class FiatMoneyField(models.DecimalField):
    def __init__(self, verbose_name=None, name=None, max_digits=12, decimal_places=2, **kwargs):
        super().__init__(verbose_name, name, max_digits, decimal_places, **kwargs)


class RichTextField(models.TextField):
    pass


class TextSerialField(serializers.CharField):
    pass


class RichTextSerialField(serializers.CharField):
    pass


class JsonSerialField(serializers.JSONField):
    def to_internal_value(self, data):
        try:
            if isinstance(data, bytes):
                data = data.decode()
            return json.loads(data, cls=self.decoder)
        except (TypeError, ValueError):
            self.fail('invalid')

    def to_representation(self, value):
        value = json.dumps(value, cls=self.encoder, indent=2)
        return value


class ImageSerialField(FileField):
    default_error_messages = {
        'invalid_image': _(
            'Upload a valid image. The file you uploaded was either not an image or a corrupted image.'
        ),
    }

    def _get_content_as_fo(self, data):
        mimetype, b64data = data.split('base64,')
        content = base64.b64decode(b64data)
        content = BytesIO(content)
        content.seek(0)
        return content

    def to_internal_value(self, data):
        # Image validation is a bit grungy, so we'll just outright
        # defer to Django's implementation so we don't need to
        # consider it, or treat PIL as a test dependency.
        fo = DjangoFile(self._get_content_as_fo(data['data']), data['name'])
        file_object = super().to_internal_value(fo)
        django_field = SVGAndImageFieldForm()
        django_field.error_messages = self.error_messages
        return django_field.clean(file_object)


class DjangoEncodedJSONField(JSONField):
    """
    Able to serialize decimals
    """

    def __init__(self, verbose_name=None, name=None, **kwargs):
        kwargs['encoder'] = DjangoJSONEncoder
        super().__init__(verbose_name, name, **kwargs)


@contextlib.contextmanager
def suppress_autotime(model, fields):
    _original_values = {}
    for field in model._meta.local_fields:
        if field.name in fields:
            _original_values[field.name] = {
                'auto_now': field.auto_now,
                'auto_now_add': field.auto_now_add,
            }
            field.auto_now = False
            field.auto_now_add = False
    try:
        yield
    finally:
        for field in model._meta.local_fields:
            if field.name in fields:
                field.auto_now = _original_values[field.name]['auto_now']
                field.auto_now_add = _original_values[field.name]['auto_now_add']


class TimestampSerializerField(serializers.Field):
    def to_representation(self, value):
        return time.mktime(value.timetuple())


def validate_svg(f):
    # Find "start" word in file and get "tag" from there
    f.seek(0)
    tag = None
    try:
        for event, el in et.iterparse(f, ('start',)):
            tag = el.tag
            break
    except et.ParseError:
        pass

    # Check that this "tag" is correct
    if tag != '{http://www.w3.org/2000/svg}svg':
        raise ValidationError('Uploaded file is not an image or SVG file.')

    # Do not forget to "reset" file
    f.seek(0)
    return f


def validate_image_file_extension(value):
    return FileExtensionValidator(allowed_extensions=get_available_image_extensions() + ['svg'])(value)


class SVGAndImageFieldForm(forms.ImageField):
    default_validators = [validate_image_file_extension]

    def to_python(self, data):
        try:
            f = super().to_python(data)
        except ValidationError:
            return validate_svg(data)
        return f


class SVGAndImageField(models.ImageField):
    def formfield(self, **kwargs):
        defaults = {'form_class': SVGAndImageFieldForm}
        defaults.update(kwargs)
        return super().formfield(**defaults)
