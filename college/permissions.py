"""
Custom permission classes for college authentication
"""
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken
from api.models import College


class IsCollegeAuthenticated(IsAuthenticated):
    """
    Permission class that ensures request is authenticated as a college using JWT token.
    Extends IsAuthenticated to leverage DRF's built-in authentication processing.
    This properly validates JWT tokens with college_id claim through CollegeJWTAuthentication.
    """

    def has_permission(self, request, view):
        """
        Check if request has valid authentication (will be processed by CollegeJWTAuthentication).
        Then verify it's a college token.
        """
        # First, ensure authentication is processed (inherits from IsAuthenticated)
        if not super().has_permission(request, view):
            return False

        # Check if request.user is a CollegeUser (has college_id or is_college attribute)
        if hasattr(request.user, 'college_id'):
            return True

        if hasattr(request.user, 'is_college') and request.user.is_college:
            return True

        # If not a college user, deny access
        return False
