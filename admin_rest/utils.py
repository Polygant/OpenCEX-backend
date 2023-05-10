import logging
import os
import random
import string
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.core.files.storage import DefaultStorage
from django.db.models import Q
from django.template.defaultfilters import slugify

from lib.helpers import BOT_RE

log = logging.getLogger(__name__)


VALID_IMAGE_EXTENSION = settings.VALID_IMAGE_EXTENSION or ['jpg', 'jpeg', 'png', 'gif']


def get_bots_ids():
    return list(User.objects.filter(username__iregex=BOT_RE).values_list('id', flat=True))


def get_user_permissions(user):
    user_permissions = []
    if user.is_superuser:
        user_permissions = ['admin']
    elif user.is_staff:
        user_permissions_qs = Permission.objects.filter(
            Q(group__in=user.groups.all()) | Q(user=user)
        ).distinct()
        for p in user_permissions_qs:
            action, model_name = p.codename.split('_', 1)
            user_permissions.append(f'{p.content_type.app_label}_{model_name}_{action}')
    return user_permissions


def is_valid_image_extension(file_path):
    extension = os.path.splitext(file_path.lower())[1]
    return extension in VALID_IMAGE_EXTENSION


def is_valid_image(file):
    if not is_valid_image_extension(file.name):
        return False

    from PIL import Image

    is_valid = False

    try:
        image = Image.open(file)
        image.verify()
        is_valid = True
    except Exception as e:
        log.exception(e)
    finally:
        file.seek(0)

    return is_valid


def get_media_url(path):
    """
    Determine system file's media URL.
    """
    return DefaultStorage().url(path)


def slugify_filename(filename):
    """ Slugify filename """
    name, ext = os.path.splitext(filename)
    slugified = get_slugified_name(name)
    return slugified + ext


def get_slugified_name(name):
    """ Slugify name """
    slugified = slugify(name)
    return slugified or get_random_string()


def get_random_string():
    return ''.join(random.sample(string.ascii_lowercase * 6, 6))


def get_upload_filename(upload_name):
    """Generates unique filename"""
    date_path = datetime.now().strftime("%Y/%m/%d")
    upload_path = os.path.join(settings.VUE_UPLOAD_PATH, date_path)
    upload_name = slugify_filename(upload_name)
    return DefaultStorage().get_available_name(os.path.join(upload_path, upload_name))


def get_image_files(path=''):
    images = []
    browse_path = os.path.join(settings.VUE_UPLOAD_PATH, path)
    for root, dirs, files in os.walk(browse_path):
        images.extend([os.path.join(f_name) for f_name in files if is_valid_image_extension(f_name)])
    return images
