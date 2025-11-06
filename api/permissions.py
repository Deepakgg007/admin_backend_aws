from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        return False


class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Allow staff users OR college users (authenticated via college login)
        if request.user and request.user.is_staff:
            return True
        # Check if this is a college user (has college attribute)
        if request.user and hasattr(request.user, 'college'):
            return True
        return False


class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows read-only access to everyone (including unauthenticated users),
    but only allows superusers/staff to create, update, or delete.
    """
    def has_permission(self, request, view):
        # Allow GET, HEAD, OPTIONS requests for all users (authenticated or not)
        if request.method in permissions.SAFE_METHODS:
            return True

        # Only superusers and staff can create, update, delete
        return request.user and (request.user.is_superuser or request.user.is_staff)


class IsSuperUserOnly(permissions.BasePermission):
    """
    Permission class that only allows superusers to perform any action.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser