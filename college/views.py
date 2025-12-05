"""
College App Views
All college-related views organized in one place
"""
from datetime import timedelta
from rest_framework import generics, status, filters
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse

from api.models import College
from api.utils import StandardResponseMixin, CustomPagination
from .serializers import (
    CollegeLoginSerializer,
    CollegeLoginResponseSerializer,
    StudentApprovalListSerializer,
    StudentApprovalActionSerializer,
    StudentDetailWithApprovalSerializer
)
from .permissions import IsCollegeAuthenticated

User = get_user_model()


def get_college_id_from_token(request):
    """
    Extract college_id from JWT token
    Returns college_id (UUID string) or None
    """
    college_id = None

    # Try to get from request.auth.payload (if token is already decoded)
    if hasattr(request, 'auth') and request.auth:
        if hasattr(request.auth, 'payload'):
            college_id = request.auth.payload.get('college_id')
        elif isinstance(request.auth, dict):
            college_id = request.auth.get('college_id')

    # If not found, decode token from Authorization header
    if not college_id:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                token = auth_header.split(' ')[1]
                decoded_token = AccessToken(token)
                college_id = decoded_token.get('college_id')
            except Exception:
                pass

    return college_id


class CollegeLoginView(APIView, StandardResponseMixin):
    """College login endpoint"""
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['College - Authentication'],
        request=CollegeLoginSerializer,
        responses={
            200: CollegeLoginResponseSerializer,
            400: OpenApiResponse(description='Invalid credentials')
        },
        summary="College Login",
        description="Login for colleges using email and password. Returns JWT tokens and college information."
    )
    def post(self, request, *args, **kwargs):
        serializer = CollegeLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        college = serializer.validated_data['college']
        remember_me = serializer.validated_data.get('remember_me', False)

        class CollegeUser:
            def __init__(self, college):
                self.id = college.id
                self.pk = college.id
                self.is_active = college.is_active
                self.email = college.email

            @property
            def is_anonymous(self):
                return False

            @property
            def is_authenticated(self):
                return True

        college_user = CollegeUser(college)
        refresh = RefreshToken.for_user(college_user)

        if remember_me:
            refresh.set_exp(lifetime=timedelta(days=30))
            refresh.access_token.set_exp(lifetime=timedelta(days=7))

        refresh['user_type'] = 'college'
        refresh['college_id'] = str(college.college_id)
        refresh['email'] = college.email

        response_data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'college': {
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
                'logo': request.build_absolute_uri(college.logo.url) if college.logo else None,
            }
        }

        return self.success_response(data=response_data, message="College login successful.")


# Student Approval Views
class PendingStudentsView(generics.ListAPIView, StandardResponseMixin):
    serializer_class = StudentApprovalListSerializer
    permission_classes = [IsCollegeAuthenticated]
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'first_name', 'last_name', 'usn']
    ordering = ['-created_at']

    @extend_schema(
        tags=['College - Student Approval'],
        summary="Get pending students for college",
        description="Returns list of students pending approval for the authenticated college from JWT token"
    )
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(self.request.user, 'college') or self.request.user.college is None:
            return User.objects.none()

        college = self.request.user.college
        # Only show students (not staff/admins) registered to this college
        return User.objects.filter(
            college=college,
            approval_status='pending',
            is_staff=False,  # Exclude staff/admins
            is_superuser=False  # Exclude superusers
        ).select_related('college').order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return self.success_response(data=serializer.data, message="Pending students retrieved.")


class StudentApprovalActionView(APIView, StandardResponseMixin):
    permission_classes = [IsCollegeAuthenticated]

    def get_serializer_class(self):
        from .serializers import StudentApprovalActionSerializer
        return StudentApprovalActionSerializer

    @extend_schema(
        tags=['College - Student Approval'],
        summary="Manage student approval status",
        description="Approve, decline, or move student to pending status. Can be used to change status from any current state (pending, approved, rejected) to any other state. Student counts are automatically managed."
    )
    def post(self, request, student_id):
        from .serializers import StudentApprovalActionSerializer, StudentDetailWithApprovalSerializer

        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(request.user, 'college') or request.user.college is None:
            return self.error_response(message="Authentication required. Please login as college.", status_code=status.HTTP_401_UNAUTHORIZED)

        college = request.user.college

        try:
            student = User.objects.get(id=student_id, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return self.error_response(message="Student not found.", status_code=status.HTTP_404_NOT_FOUND)

        if student.college != college:
            return self.error_response(message="Not authorized to manage this student.", status_code=status.HTTP_403_FORBIDDEN)

        if student.is_staff or student.is_superuser:
            return self.error_response(message="Cannot manage staff or admin users.", status_code=status.HTTP_403_FORBIDDEN)

        # Allow status changes from any status (pending, approved, rejected)
        current_status = student.approval_status

        serializer = StudentApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']

        # Handle student count changes based on status transitions
        if action == 'approve':
            student.approval_status = 'approved'
            student.is_verified = True
            student.rejection_reason = ''  # Clear any previous rejection reason
            
            # Only increment count if student wasn't already approved
            if current_status != 'approved':
                college.current_students = F('current_students') + 1
                college.save()
            
            message = f"{student.get_full_name()} approved successfully."
            
        elif action == 'decline':
            student.approval_status = 'rejected'
            student.is_verified = False
            student.rejection_reason = serializer.validated_data.get('decline_reason', '')
            
            # Decrement count if student was previously approved
            if current_status == 'approved':
                college.current_students = F('current_students') - 1
                college.save()
            
            message = f"{student.get_full_name()} declined."
            
        elif action == 'pending':
            student.approval_status = 'pending'
            student.is_verified = False
            student.rejection_reason = ''  # Clear any rejection reason
            
            # Decrement count if student was previously approved
            if current_status == 'approved':
                college.current_students = F('current_students') - 1
                college.save()
            
            message = f"{student.get_full_name()} moved to pending status."

        student.approved_by = college
        student.approval_date = timezone.now()
        student.save()

        response_serializer = StudentDetailWithApprovalSerializer(student)
        return self.success_response(data=response_serializer.data, message=message)


class StudentDeleteView(APIView, StandardResponseMixin):
    """Delete a student registered to the college"""
    permission_classes = [IsCollegeAuthenticated]

    @extend_schema(
        tags=['College - Student Approval'],
        summary="Delete student",
        description="Delete a student who registered to the authenticated college. This permanently removes the student account."
    )
    def delete(self, request, student_id):
        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(request.user, 'college') or request.user.college is None:
            return self.error_response(message="Authentication required. Please login as college.", status_code=status.HTTP_401_UNAUTHORIZED)

        college = request.user.college

        try:
            student = User.objects.get(id=student_id, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return self.error_response(message="Student not found.", status_code=status.HTTP_404_NOT_FOUND)

        if student.college != college:
            return self.error_response(message="Not authorized to delete this student.", status_code=status.HTTP_403_FORBIDDEN)

        if student.is_staff or student.is_superuser:
            return self.error_response(message="Cannot delete staff or admin users.", status_code=status.HTTP_403_FORBIDDEN)

        student_name = student.get_full_name()
        student_email = student.email

        # Decrement college's current_students count if student was approved
        if student.approval_status == 'approved':
            college.current_students = F('current_students') - 1
            college.save()
            college.refresh_from_db()

        # Delete the student
        student.delete()

        return self.success_response(
            data={
                'deleted_student': {
                    'name': student_name,
                    'email': student_email
                }
            },
            message=f"Student {student_name} deleted successfully."
        )


class CollegeStudentCountView(APIView, StandardResponseMixin):
    """Get student count statistics and list for a college"""
    permission_classes = [IsCollegeAuthenticated]

    @extend_schema(
        tags=['College - Student Approval'],
        summary="Get student count and list for college",
        description="Returns the count and list of students (pending, approved, rejected, total) for the authenticated college from JWT token"
    )
    def get(self, request):
        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(request.user, 'college') or request.user.college is None:
            return self.error_response(message="Authentication required. Please login as college.", status_code=status.HTTP_401_UNAUTHORIZED)

        college = request.user.college

        # Get all students (not staff/admins) for this college
        all_students = User.objects.filter(
            college=college,
            is_staff=False,  # Exclude staff/admins
            is_superuser=False  # Exclude superusers
        ).select_related('college').order_by('-created_at')

        # Get counts for different statuses
        pending_students = all_students.filter(approval_status='pending')
        approved_students = all_students.filter(approval_status='approved')
        rejected_students = all_students.filter(approval_status='rejected')

        # Serialize student lists
        from .serializers import StudentApprovalListSerializer

        serializer_context = {'request': request}

        data = {
            'college_id': str(college.college_id),
            'college_name': college.name,
            'statistics': {
                'pending_count': pending_students.count(),
                'approved_count': approved_students.count(),
                'rejected_count': rejected_students.count(),
                'total_count': all_students.count(),
                'max_students': college.max_students,
                'available_seats': college.available_seats,
            },
            'students': {
                'pending': StudentApprovalListSerializer(pending_students, many=True, context=serializer_context).data,
                'approved': StudentApprovalListSerializer(approved_students, many=True, context=serializer_context).data,
                'rejected': StudentApprovalListSerializer(rejected_students, many=True, context=serializer_context).data,
            }
        }

        return self.success_response(data=data, message="Student count and list retrieved successfully.")


# ============================================
# COLLEGE FORGOT PASSWORD VIEWS
# ============================================

class CollegeForgotPasswordRequestView(APIView, StandardResponseMixin):
    """Request OTP for college password reset"""
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        from .serializers import ForgotPasswordRequestSerializer
        return ForgotPasswordRequestSerializer

    @extend_schema(
        tags=['College - Password Reset'],
        responses={
            200: OpenApiResponse(description='OTP sent successfully'),
            400: OpenApiResponse(description='Invalid email or college not found')
        },
        summary="Request Password Reset OTP",
        description="Send OTP to registered college email for password reset"
    )
    def post(self, request):
        from api.utils import create_otp_record, send_otp_email
        from .serializers import ForgotPasswordRequestSerializer

        serializer = ForgotPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Check if college exists
        try:
            college = College.objects.get(email=email, is_active=True)
        except College.DoesNotExist:
            return self.error_response(
                message="No active college found with this email address.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # Create OTP record
        otp = create_otp_record(email, otp_type='college')

        # Send OTP email
        email_sent = send_otp_email(email, otp.otp_code, user_type='college')

        if not email_sent:
            return self.error_response(
                message="Failed to send OTP email. Please try again.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return self.success_response(
            message=f"OTP has been sent to {email}. Please check your inbox.",
            data={"email": email}
        )


class CollegeVerifyOTPView(APIView, StandardResponseMixin):
    """Verify OTP for college password reset"""
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        from .serializers import VerifyOTPSerializer
        return VerifyOTPSerializer

    @extend_schema(
        tags=['College - Password Reset'],
        responses={
            200: OpenApiResponse(description='OTP verified successfully'),
            400: OpenApiResponse(description='Invalid or expired OTP')
        },
        summary="Verify OTP",
        description="Verify the OTP code sent to college email"
    )
    def post(self, request):
        from api.utils import verify_otp
        from .serializers import VerifyOTPSerializer

        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']

        # Verify OTP
        is_valid, message = verify_otp(email, otp_code, otp_type='college')

        if not is_valid:
            return self.error_response(message=message, status_code=status.HTTP_400_BAD_REQUEST)

        return self.success_response(
            message="OTP verified successfully. You can now reset your password.",
            data={"email": email}
        )


class CollegeResetPasswordView(APIView, StandardResponseMixin):
    """Reset college password with verified OTP"""
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        from .serializers import ResetPasswordSerializer
        return ResetPasswordSerializer

    @extend_schema(
        tags=['College - Password Reset'],
        responses={
            200: OpenApiResponse(description='Password reset successfully'),
            400: OpenApiResponse(description='Invalid OTP or college not found')
        },
        summary="Reset Password",
        description="Reset college password using verified OTP"
    )
    def post(self, request):
        from authentication.models import OTP
        from django.contrib.auth.hashers import make_password
        from .serializers import ResetPasswordSerializer

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']
        new_password = serializer.validated_data['new_password']

        # Check if OTP is verified
        try:
            otp = OTP.objects.get(
                email=email,
                otp_code=otp_code,
                otp_type='college',
                is_verified=True
            )

            if otp.is_expired():
                return self.error_response(
                    message="OTP has expired. Please request a new one.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

        except OTP.DoesNotExist:
            return self.error_response(
                message="Invalid or unverified OTP. Please verify your OTP first.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Get college and reset password
        try:
            college = College.objects.get(email=email, is_active=True)
            college.password = make_password(new_password)
            college.save()

            # Delete used OTP
            OTP.objects.filter(email=email, otp_type='college').delete()

            return self.success_response(
                message="Password reset successfully. You can now login with your new password.",
                data={"email": email}
            )

        except College.DoesNotExist:
            return self.error_response(
                message="College not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )


# ============================================
# ENROLLED STUDENTS VIEWS
# ============================================

class EnrolledStudentsListView(generics.ListAPIView, StandardResponseMixin):
    """
    List all students enrolled in courses created by this college
    Includes enrollment details and completion progress
    """
    permission_classes = [IsCollegeAuthenticated]  # Authentication via JWT token
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'student__email', 'student__usn', 'course__title']
    ordering_fields = ['enrolled_at', 'progress_percentage', 'status', 'course__title', 'student__first_name']
    ordering = ['-enrolled_at']

    def get_serializer_class(self):
        from .serializers import EnrolledStudentSerializer
        return EnrolledStudentSerializer

    def get_queryset(self):
        """Get enrollments for all students belonging to this college"""
        from courses.models import Enrollment

        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(self.request.user, 'college') or self.request.user.college is None:
            return Enrollment.objects.none()

        college = self.request.user.college

        # Get enrollments for students belonging to this college (regardless of course creator)
        queryset = Enrollment.objects.filter(
            student__college=college
        ).select_related(
            'student',
            'course'
        ).order_by('-enrolled_at')

        # Optional filters
        course_id = self.request.query_params.get('course', None)
        status_filter = self.request.query_params.get('status', None)

        if course_id:
            queryset = queryset.filter(course_id=course_id)

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    @extend_schema(
        tags=['College - Enrolled Students'],
        summary="List enrolled students",
        description="Get list of all students enrolled in courses created by this college with their progress details"
    )
    def list(self, request, *args, **kwargs):
        """Override list to provide custom response format"""
        queryset = self.filter_queryset(self.get_queryset())

        # Get college from authenticated request (set by IsCollegeAuthenticated permission)
        if not hasattr(request.user, 'college') or request.user.college is None:
            return self.error_response(
                message="Authentication required. Please login as college.",
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        # Calculate progress for each enrollment before serializing
        for enrollment in queryset:
            old_progress = enrollment.progress_percentage
            enrollment.calculate_progress()
            new_progress = enrollment.progress_percentage

            # Debug logging
            import sys
            print(f"[PROGRESS_DEBUG] Student: {enrollment.student.email}, Course: {enrollment.course.title}, Old: {old_progress}%, New: {new_progress}%", file=sys.stderr)

            enrollment.save(update_fields=['progress_percentage', 'status', 'completed_at'])

        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            # Get pagination info
            paginator = self.paginator
            pagination_data = {
                'total': paginator.page.paginator.count,
                'page': paginator.page.number,
                'per_page': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
            }

            return self.success_response(
                data=serializer.data,
                message="Enrolled students retrieved successfully.",
                pagination=pagination_data
            )

        # Non-paginated response
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Enrolled students retrieved successfully."
        )


class EngagementStatsView(APIView, StandardResponseMixin):
    """
    Get simplified engagement statistics for college dashboard
    - Active Students: Count of approved students with is_active=1
    - Enrolled Students: Count of unique students enrolled in at least one course
    - Inactive Students: Count of approved students with is_active=0
    """
    permission_classes = [IsCollegeAuthenticated]

    @extend_schema(
        tags=['College - Statistics'],
        summary="Get engagement statistics",
        description="Get simplified engagement stats: active, enrolled, and inactive student counts"
    )
    def get(self, request, *args, **kwargs):
        """Get simplified engagement statistics"""

        # Get college from authenticated request
        if not hasattr(request.user, 'college') or request.user.college is None:
            return self.error_response(
                message="Authentication required. Please login as college.",
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        college = request.user.college

        # 1. Active Students: Approved students with is_active=1
        active_students = User.objects.filter(
            college=college,
            approval_status='approved',
            is_active=True
        ).count()

        # 2. Enrolled Students: Unique students with at least one enrollment in college's courses
        from courses.models import Enrollment
        enrolled_students = Enrollment.objects.filter(
            course__college=college
        ).values('student').distinct().count()

        # 3. Inactive Students: Approved students with is_active=0
        inactive_students = User.objects.filter(
            college=college,
            approval_status='approved',
            is_active=False
        ).count()

        return self.success_response(
            data={
                'active_students': active_students,
                'enrolled_students': enrolled_students,
                'inactive_students': inactive_students,
            },
            message="Engagement statistics retrieved successfully."
        )
