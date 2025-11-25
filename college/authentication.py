"""
Custom authentication for college login
Handles JWT tokens with college_id instead of user_id
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from api.models import College


class CollegeJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that handles both:
    1. Regular user tokens (user_id)
    2. College tokens (college_id)
    """

    def get_user(self, validated_token):
        """
        Override to check if token is for a college or a user
        """
        # Check if this is a college token
        user_type = validated_token.get('user_type')

        if user_type == 'college':
            # This is a college token
            college_id = validated_token.get('college_id')
            if not college_id:
                raise InvalidToken('Token does not contain college_id')

            try:
                college = College.objects.get(college_id=college_id, is_active=True)
            except College.DoesNotExist:
                raise AuthenticationFailed('College not found or not active')

            # Create a fake user object for DRF
            class CollegeUser:
                def __init__(self, college):
                    self._id = college.id
                    self._pk = college.id
                    self.is_active = college.is_active
                    self.email = college.email
                    self.username = college.email  # Use email as username
                    self.first_name = college.name.split()[0] if college.name else ''
                    self.last_name = ' '.join(college.name.split()[1:]) if college.name and len(college.name.split()) > 1 else ''
                    self.college_id = college.college_id
                    self.college = college
                    self.is_staff = False
                    self.is_superuser = False
                    self.is_college = True

                @property
                def id(self):
                    return self._id

                @property
                def pk(self):
                    return self._pk

                @property
                def is_anonymous(self):
                    return False

                @property
                def is_authenticated(self):
                    return True

                def __int__(self):
                    """Allow casting to int for database queries"""
                    return self._id

                def __str__(self):
                    return f"CollegeUser({self.email})"

            return CollegeUser(college)
        else:
            # Regular user token - use default behavior
            return super().get_user(validated_token)
