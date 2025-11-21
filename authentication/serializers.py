from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    college_name_display = serializers.SerializerMethodField()
    college_details = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()


    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name',
                 'phone_number', 'date_of_birth', 'profile_picture', 'bio',
                 'usn', 'college', 'college_name', 'college_name_display',
                 'college_details', 'is_verified', 'is_staff', 'is_superuser',
                 'is_admin', 'approval_status', 'rejection_reason',
                 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_verified',
                           'is_staff', 'is_superuser', 'is_admin', 'college_name_display',
                           'approval_status', 'rejection_reason')

    def get_college_name_display(self, obj):
        # Handle both regular User objects and CollegeUser authentication objects
        if hasattr(obj, 'get_college_display'):
            return obj.get_college_display()
        elif hasattr(obj, 'is_college') and obj.is_college:
            # CollegeUser - return college name
            if hasattr(obj, 'college') and obj.college:
                return obj.college.name
        return None

    def get_college_details(self, obj):
        if obj.college:
            # Get the request to build absolute URL for logo
            request = self.context.get('request')
            logo_url = None
            if obj.college.logo:
                if request:
                    logo_url = request.build_absolute_uri(obj.college.logo.url)
                else:
                    logo_url = obj.college.logo.url

            return {
                'id': obj.college.id,
                'name': obj.college.name,
                'organization': obj.college.organization.name,
                'university': obj.college.organization.university.name,
                'is_active': obj.college.is_active,
                'logo': logo_url
            }
        return None

    def get_is_admin(self, obj):
        """Check if user is admin (staff or superuser)"""
        return obj.is_staff or obj.is_superuser


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    college = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    college_name = serializers.CharField(required=False, allow_blank=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True, use_url=True)
    usn = serializers.CharField(required=True, help_text="University Serial Number is required")

    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password2', 'first_name',
                 'last_name', 'phone_number', 'date_of_birth', 'usn',
                 'college', 'college_name', 'profile_picture')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        # Validate USN is required and unique
        if not attrs.get('usn') or not attrs['usn'].strip():
            raise serializers.ValidationError({"usn": "USN (University Serial Number) is required."})

        if User.objects.filter(usn=attrs['usn']).exists():
            raise serializers.ValidationError({"usn": "USN already exists. Please use a different USN."})

        # Validate college ID if provided
        if 'college' in attrs and attrs['college'] is not None:
            from api.models import College
            try:
                college = College.objects.get(id=attrs['college'])
                attrs['college'] = college
            except College.DoesNotExist:
                raise serializers.ValidationError({"college": "College not found."})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user
    
    def to_internal_value(self, data):
        # Handle profile_picture field - if it's a string "null" or "Null", treat it as None
        if 'profile_picture' in data:
            if data['profile_picture'] in ['null', 'Null', 'NULL', '', None]:
                data = data.copy()  # Create a mutable copy
                data.pop('profile_picture', None)  # Remove the logo field
        return super().to_internal_value(data)


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    college = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone_number', 'date_of_birth',
                 'profile_picture', 'bio', 'usn', 'college', 'college_name')

    def validate_usn(self, value):
        if value:
            # Check if USN is already taken by another user
            user = self.context['request'].user if 'request' in self.context else self.instance
            if User.objects.filter(usn=value).exclude(id=user.id).exists():
                raise serializers.ValidationError("USN already exists.")
        return value

    def validate_college(self, value):
        if value is not None:
            from api.models import College
            try:
                college = College.objects.get(id=value)
                return college
            except College.DoesNotExist:
                raise serializers.ValidationError("College not found.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    remember_me = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError('Must include email and password')

        # First check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'email': 'No account found with this email address. Please register.'
            })

        # Then authenticate with password
        authenticated_user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )

        if not authenticated_user:
            raise serializers.ValidationError({
                'password': 'Incorrect password. Please try again.'
            })

        attrs['user'] = authenticated_user
        return attrs


class LoginResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


# Forgot Password Serializers

class ForgotPasswordRequestSerializer(serializers.Serializer):
    """Serializer for requesting OTP for password reset"""
    email = serializers.EmailField()

    def validate_email(self, value):
        # This will be validated in the view based on user_type
        return value


class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP code"""
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)

    def validate_otp_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value


class ResetPasswordSerializer(serializers.Serializer):
    """Serializer for resetting password with OTP"""
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs
