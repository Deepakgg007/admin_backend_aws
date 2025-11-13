from rest_framework import permissions


class IsSuperUserOrStaff(permissions.BasePermission):
    """
    Only staff/admin users can access.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff
