from rest_framework import permissions


class IsPUTOrIsAuthenticated(permissions.IsAuthenticated):

    def has_permission(self, request, view):
        # Read permission - always allow for POST request
        if request.method in ['PUT']:
            return True

        # Write permissions - only if authenticated
        return super().has_permission(request, view)
