from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

import os


def upload_to(instance, filename):
    now_time = now()
    base, extension = os.path.splitext(filename.lower())
    milliseconds = now_time.microsecond // 1000
    return f"uploads/announces/{now_time:%Y%m%d%H%M%S}{milliseconds}{extension}"


def validate_extension(obj):
    base, extension = os.path.splitext(obj.name.lower())
    if extension in settings.VALID_IMAGE_EXTENSION:
        return obj
    else:
        raise ValidationError({
            'message': _("This field can only have the format [png, jpg, jpeg]"),
            'type': 'img_format_incorrect'
        })
