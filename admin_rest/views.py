import logging

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User, Group
from django.core.files.storage import DefaultStorage
from django.http import JsonResponse
from django_otp import match_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from admin_rest import restful_admin as api_admin
from admin_rest.serializers import UserDetailsSerializer
from admin_rest.utils import is_valid_image, get_media_url, get_upload_filename, get_image_files

log = logging.getLogger(__name__)

from rest_framework_simplejwt.tokens import RefreshToken


DEVICE_ID_SESSION_KEY = 'otp_device_id'


@api_view(['POST'])
@permission_classes((AllowAny, ))
def login(request):
    """Authenticate user.
    Returns access token.
    """
    error = {'status': False, 'error': 'Incorrect username or password'}
    error_response = JsonResponse(error, safe=False, status=status.HTTP_400_BAD_REQUEST)

    username = request.data.get('username')
    password = request.data.get('password')
    if not username or not password:
        return error_response
    # Identity
    user = User.objects.filter(username=username, is_active=True).first()
    if not user:
        return error_response
    # Auth
    user = authenticate(username=user.username, password=password)
    if not user:
        return error_response

    if not user.is_active:
        return error_response

    if not user.is_superuser and not user.is_staff:
        return error_response

    # check 2FA
    if settings.ENABLE_OTP_ADMIN:
        otp_token = request.data.get('otp_token')
        if otp_token and otp_token.isdigit():
            otp_token = int(otp_token)
        device = match_token(user, otp_token)
        if not device:
            error['error'] = 'Incorrect 2FA token'
            return JsonResponse(error, safe=False, status=status.HTTP_400_BAD_REQUEST)

        request.session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        request.user.otp_device = device

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)

    response = JsonResponse({'status': True, 'access_token': access_token, 'refresh_token': refresh_token}, safe=False, status=status.HTTP_200_OK)
    response.set_cookie(settings.JWT_AUTH_COOKIE, access_token, settings.JWT_EXPIRATION_DELTA.total_seconds(), httponly=True)

    return response


@api_view(['POST', 'PUT'])
def permissions(request):
    """Add/change permissions of selected group"""
    user = request.user
    if not (user.is_staff and user.is_superuser and user.is_active):
        return JsonResponse({'status': False}, safe=False, status=status.HTTP_403_FORBIDDEN)

    # serializer = GroupSerializer(request.data)
    # serializer.is_valid(True)

    group_id = request.data.get('id')
    group_name = request.data.get('name')
    group_permissions = request.data.get('permissions')
    users = request.data.get('users')

    if request.method == 'PUT':
        if not group_id or not group_permissions:
            return JsonResponse({'status': False}, safe=False, status=status.HTTP_400_BAD_REQUEST)

        group = Group.objects.get(id=group_id)
        if not group:
            return JsonResponse({'status': False, 'error': 'Group not found'},
                                safe=False, status=status.HTTP_400_BAD_REQUEST)
        group.name = group_name
        group.save()

    elif request.method == 'POST':
        group = Group.objects.create(name=group_name)

    selected_permissions_ids = []
    all_permissions_dict = {f'{p.content_type.app_label}/{p.content_type.model}/{p.codename.split("_")[0]}': p.id
                            for p in Permission.objects.all()}

    for group_perm in group_permissions:
        for act, act_perm in group_perm['permissions'].items():
            if act_perm:
                name = group_perm['modelName'] + '/' + act
                if name in all_permissions_dict:
                    selected_permissions_ids.append(all_permissions_dict[name])

    group.permissions.set(selected_permissions_ids)
    group.user_set.set(users)
    response = JsonResponse({'status': True}, safe=False, status=status.HTTP_200_OK)
    return response


@api_view(['GET'])
def me(request):
    """Current user info"""
    user = request.user
    user_data = UserDetailsSerializer(user).data
    response = JsonResponse({'status': True, 'user': user_data}, safe=False, status=status.HTTP_200_OK)
    return response


@api_view(['GET'])
def models(request):
    """List of all registered models names in form: ['<app_name>/<model_name>', ...]"""
    registered_models = api_admin.site.get_registered_models()
    return JsonResponse(registered_models, safe=False, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes((AllowAny, ))
def resources(request):
    """List of all registered admin resources"""
    resourses = api_admin.site.get_resources()
    return JsonResponse(resourses, safe=False, status=status.HTTP_200_OK)


@api_view(['GET'])
def navigation(request):
    """Vue admin side navigation"""
    navigation = api_admin.site.make_navigation(request.user)
    return JsonResponse(navigation, safe=False, status=status.HTTP_200_OK)


@api_view(['POST'])
@staff_member_required
def upload_image(request):
    """
    Uploads a file and send back its URL to VueAdmin.
    """
    uploaded_file = request.FILES['file']

    # checks image extension and validate image via PIL
    if not is_valid_image(uploaded_file):
        return JsonResponse({'status': False, 'error': 'Image is not valid'}, safe=False, status=status.HTTP_400_BAD_REQUEST)

    filepath = get_upload_filename(uploaded_file.name)
    saved_path = DefaultStorage().save(filepath, uploaded_file)

    url = get_media_url(saved_path)

    return JsonResponse({'location': url})


@api_view(['POST'])
@staff_member_required
def image_browser(request):
    """
    Return all uploaded images
    """

    uploaded_images = get_image_files()

    # get urls
    images = [get_media_url(i) for i in uploaded_images]

    return JsonResponse({'images': images})
