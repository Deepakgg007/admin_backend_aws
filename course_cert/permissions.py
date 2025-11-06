from rest_framework import permissions
from college.views import get_college_id_from_token
class IsSuperUserOrStaff(permissions.BasePermission):
    """
    Only staff/admin users can access.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff


class IsCollegeAuthenticated(permissions.BasePermission):
    """Allows access only to authenticated colleges via JWT"""

    def has_permission(self, request, view):
        return bool(get_college_id_from_token(request))
