from rest_framework.permissions import BasePermission


class IsSuperAdminUser(BasePermission):
    """
    Allows access only to superadmin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active and request.user.is_staff and request.user.is_superuser)