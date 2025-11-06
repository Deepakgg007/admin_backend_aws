"""
College App Serializers
All college-related serializers in one place
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from drf_spectacular.utils import extend_schema_field

from api.models import College, University, Organization

User = get_user_model()


# ============================================
# COLLEGE AUTHENTICATION SERIALIZERS
# ============================================

class CollegeLoginSerializer(serializers.Serializer):
    """Serializer for college login"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    remember_me = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        import logging
        logger = logging.getLogger(__name__)

        email = attrs.get('email')
        password = attrs.get('password')

        logger.info(f"🔍 College login attempt - Email: {email}, Has password: {bool(password)}")

        if not email or not password:
            logger.warning("❌ Missing email or password")
            raise serializers.ValidationError('Must include email and password')

        try:
            college = College.objects.get(email=email, is_active=True)
            logger.info(f"✅ College found: {college.name}")

            if not college.check_password(password):
                logger.warning(f"❌ Invalid password for {email}")
                raise serializers.ValidationError('Invalid credentials')

            logger.info(f"✅ Password valid for {email}")
        except College.DoesNotExist:
            logger.warning(f"❌ College not found with email: {email}")
            raise serializers.ValidationError('Invalid credentials')

        attrs['college'] = college
        return attrs


class CollegeLoginResponseSerializer(serializers.Serializer):
    """Response serializer for college login"""
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    college = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField())
    def get_college(self, obj):
        college = obj.get('college')
        return {
            'id': college.id,
            'college_id': str(college.college_id),
            'name': college.name,
            'email': college.email,
            'organization': college.organization.name,
            'university': college.organization.university.name,
            'max_students': college.max_students,
            'current_students': college.current_students,
            'available_seats': college.available_seats,
            'is_registration_open': college.is_registration_open,
        }


# ============================================
# COLLEGE FORGOT PASSWORD SERIALIZERS
# ============================================

class ForgotPasswordRequestSerializer(serializers.Serializer):
    """Serializer for requesting OTP for password reset"""
    email = serializers.EmailField()


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


# ============================================
# STUDENT APPROVAL SERIALIZERS
# ============================================

class StudentApprovalListSerializer(serializers.ModelSerializer):
    """Serializer for listing students pending approval"""
    college_name = serializers.CharField(source='college.name', read_only=True)
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'usn', 'phone_number', 'college', 'college_name',
            'approval_status', 'created_at', 'profile_picture'
        ]
        read_only_fields = ['id', 'created_at', 'approval_status']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_profile_picture(self, obj):
        """Return absolute URL for profile picture"""
        request = self.context.get('request')
        if obj.profile_picture:
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None


class StudentApprovalActionSerializer(serializers.Serializer):
    """Serializer for approving/declining students"""
    ACTION_CHOICES = [
        ('approve', 'Approve'),
        ('decline', 'Decline'),
        ('pending', 'Move to Pending'),
    ]

    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    decline_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] == 'decline' and not attrs.get('decline_reason'):
            raise serializers.ValidationError({
                "decline_reason": "Decline reason is required when declining a student."
            })
        return attrs


class StudentDetailWithApprovalSerializer(serializers.ModelSerializer):
    """Detailed serializer with approval info"""
    college_details = serializers.SerializerMethodField()
    approved_by_details = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'date_of_birth', 'profile_picture', 'bio',
            'usn', 'college', 'college_name', 'college_details',
            'approval_status', 'approved_by', 'approved_by_details',
            'approval_date', 'rejection_reason', 'is_verified',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approval_date',
            'is_verified', 'created_at', 'updated_at'
        ]

    @extend_schema_field(serializers.DictField())
    def get_college_details(self, obj):
        if obj.college:
            return {
                'id': obj.college.id,
                'name': obj.college.name,
                'organization': obj.college.organization.name,
                'university': obj.college.organization.university.name
            }
        return None

    @extend_schema_field(serializers.DictField())
    def get_approved_by_details(self, obj):
        if obj.approved_by:
            return {
                'id': obj.approved_by.id,
                'name': obj.approved_by.name,
                'email': obj.approved_by.email
            }
        return None


# ============================================
# COLLEGE MANAGEMENT SERIALIZERS
# ============================================

class CollegeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing colleges"""
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    university_name = serializers.CharField(source='organization.university.name', read_only=True)
    available_seats = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()

    class Meta:
        model = College
        fields = ['id', 'college_id', 'name', 'organization_name',
                 'university_name', 'email', 'phone_number', 'max_students',
                 'current_students', 'available_seats', 'is_registration_open',
                 'logo', 'is_active']

    @extend_schema_field(serializers.IntegerField())
    def get_available_seats(self, obj):
        return obj.available_seats

    @extend_schema_field(serializers.BooleanField())
    def get_is_registration_open(self, obj):
        return obj.is_registration_open


class CollegeDetailSerializer(serializers.ModelSerializer):
    """Detailed college serializer"""
    created_by = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    university_name = serializers.CharField(source='organization.university.name', read_only=True)
    available_seats = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    logo = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True)

    class Meta:
        model = College
        fields = ['id', 'college_id', 'organization', 'organization_name',
                 'university_name', 'name', 'email', 'password', 'address',
                 'phone_number', 'max_students', 'current_students',
                 'available_seats', 'is_registration_open', 'logo',
                 'description', 'created_by', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'college_id', 'created_by', 'created_at',
                          'updated_at', 'current_students']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    @extend_schema_field(serializers.DictField())
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'name': obj.created_by.get_full_name(),
                'email': obj.created_by.email
            }
        return None

    @extend_schema_field(serializers.IntegerField())
    def get_available_seats(self, obj):
        return obj.available_seats

    @extend_schema_field(serializers.BooleanField())
    def get_is_registration_open(self, obj):
        return obj.is_registration_open

    def create(self, validated_data):
        password = validated_data.pop('password')
        college = College.objects.create(**validated_data)
        college.password = make_password(password)
        college.save()
        return college

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.password = make_password(password)
        instance.save()
        return instance


# ============================================
# ENROLLED STUDENTS SERIALIZERS
# ============================================

class EnrolledStudentSerializer(serializers.Serializer):
    """Serializer for enrolled students with course completion details"""
    student_id = serializers.IntegerField(source='student.id')
    student_name = serializers.SerializerMethodField()
    student_email = serializers.EmailField(source='student.email')
    student_usn = serializers.CharField(source='student.usn', allow_null=True)
    student_phone = serializers.CharField(source='student.phone_number', allow_null=True)

    course_id = serializers.IntegerField(source='course.id')
    course_title = serializers.CharField(source='course.title')
    course_code = serializers.CharField(source='course.course_id', allow_null=True)

    enrollment_status = serializers.CharField(source='status')
    progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)

    enrolled_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    last_accessed = serializers.DateTimeField(allow_null=True)

    @extend_schema_field(serializers.CharField())
    def get_student_name(self, obj):
        """Get full name of student"""
        student = obj.student
        return f"{student.first_name} {student.last_name}".strip() or student.username
