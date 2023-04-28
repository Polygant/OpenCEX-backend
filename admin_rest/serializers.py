from django.contrib.auth.models import User, Permission, Group
from rest_framework import serializers

from admin_rest.utils import get_user_permissions


class UserDetailsSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj):
        return get_user_permissions(obj)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name',
                  'is_staff', 'is_superuser', 'permissions')


class PermissionSerializer(serializers.ModelSerializer):
    action = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    def get_name(self, obj):
        return f'{obj.content_type.app_label}/{obj.content_type.model}'

    def get_action(self, obj):
        return obj.codename.split('_')[0]


    class Meta:
        model = Permission
        fields = ('id', 'model_app', 'model_name', 'action')


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ('id', 'name',)


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email',)
