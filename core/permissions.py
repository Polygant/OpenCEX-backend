from rest_framework import permissions

from core.models.facade import TwoFactorSecretTokens
from core.utils.facade import is_bot_user


class Is2FAEnabled(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and \
               request.user.is_authenticated and \
               TwoFactorSecretTokens.is_enabled_for_user(request.user)


class BotsOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and \
               request.user.is_authenticated and \
               is_bot_user(request.user.username)
