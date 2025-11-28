from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from api.permissions import IsSuperUserOnly
from api.utils import StandardResponseMixin
from .services import get_dashboard_data, get_completion_report, get_students_report
from .services_student import get_student_dashboard, get_student_submission_stats


class AdminDashboardAnalyticsView(APIView, StandardResponseMixin):
    permission_classes = [IsSuperUserOnly]

    def get(self, request):
        college_id = request.query_params.get('college')

        # Convert to int if provided
        if college_id:
            try:
                college_id = int(college_id)
            except (ValueError, TypeError):
                college_id = None

        data = get_dashboard_data(college_id=college_id)
        return self.success_response(
            data=data,
            message="Analytics data retrieved successfully."
        )


class StudentDashboardView(APIView, StandardResponseMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id

        data = get_student_dashboard(user_id)
        return self.success_response(
            data=data,
            message="Student dashboard fetched successfully."
        )


class CourseCompletionReportView(APIView, StandardResponseMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        college_id = request.query_params.get('college_id')

        # Check if this is a college admin (JWT token with college_id)
        token_college_id = None
        if hasattr(request, 'auth') and request.auth:
            if hasattr(request.auth, 'payload'):
                token_college_id = request.auth.payload.get('college_id')
            elif isinstance(request.auth, dict):
                token_college_id = request.auth.get('college_id')

        # If college admin via JWT token, restrict to their college
        if token_college_id:
            try:
                from api.models import College
                college = College.objects.get(college_id=token_college_id)
                college_id = college.id
            except College.DoesNotExist:
                return self.error_response(
                    message="College not found.",
                    status_code=status.HTTP_404_NOT_FOUND
                )
        # If user is staff (college admin), only allow their college's data
        elif request.user.is_staff and not request.user.is_superuser:
            if hasattr(request.user, 'college') and request.user.college:
                college_id = request.user.college.id
            else:
                return self.error_response(
                    message="College admin must be associated with a college.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

        # Convert to int if provided (for superusers)
        if college_id:
            try:
                college_id = int(college_id)
            except (ValueError, TypeError):
                college_id = None

        data = get_completion_report(college_id=college_id)
        return self.success_response(
            data=data,
            message="Course completion report retrieved successfully."
        )


class StudentsReportView(APIView, StandardResponseMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        college_id = request.query_params.get('college_id')

        # Check if this is a college admin (JWT token with college_id)
        token_college_id = None
        if hasattr(request, 'auth') and request.auth:
            if hasattr(request.auth, 'payload'):
                token_college_id = request.auth.payload.get('college_id')
            elif isinstance(request.auth, dict):
                token_college_id = request.auth.get('college_id')

        # If college admin via JWT token, restrict to their college
        if token_college_id:
            try:
                from api.models import College
                college = College.objects.get(college_id=token_college_id)
                college_id = college.id
            except College.DoesNotExist:
                return self.error_response(
                    message="College not found.",
                    status_code=status.HTTP_404_NOT_FOUND
                )
        # If user is staff (college admin), only allow their college's data
        elif request.user.is_staff and not request.user.is_superuser:
            if hasattr(request.user, 'college') and request.user.college:
                college_id = request.user.college.id
            else:
                return self.error_response(
                    message="College admin must be associated with a college.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

        # Convert to int if provided (for superusers)
        if college_id:
            try:
                college_id = int(college_id)
            except (ValueError, TypeError):
                college_id = None

        data = get_students_report(college_id=college_id)
        return self.success_response(
            data=data,
            message="Students report retrieved successfully."
        )


class StudentSubmissionStatsView(APIView, StandardResponseMixin):
    """Get submission stats for a specific student - College admin only"""
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        # Check if user has permission to view this student's data
        # College admins can only view students from their college
        from authentication.models import CustomUser

        try:
            student = CustomUser.objects.get(id=student_id)
        except CustomUser.DoesNotExist:
            return self.error_response(
                message="Student not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # If college admin, check if student is from their college
        if request.user.is_staff and not request.user.is_superuser:
            if student.college_id != request.user.college_id:
                return self.error_response(
                    message="You don't have permission to view this student's data.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

        # Get submission stats
        submission_stats = get_student_submission_stats(student_id)

        return self.success_response(
            data=submission_stats,
            message="Student submission stats retrieved successfully."
        )


class StudentDeleteView(APIView, StandardResponseMixin):
    """Delete a student - Superuser only"""
    permission_classes = [IsSuperUserOnly]

    def delete(self, request, student_id):
        from django.contrib.auth import get_user_model
        from django.db.models import F
        from api.models import College
        
        User = get_user_model()
        
        try:
            student = User.objects.get(id=student_id, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return self.error_response(
                message="Student not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        if student.is_staff or student.is_superuser:
            return self.error_response(
                message="Cannot delete staff or admin users.",
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        student_name = student.get_full_name() or student.username
        student_email = student.email
        
        # Decrement college's current_students count if student was approved
        if student.college and student.approval_status == 'approved':
            college = student.college
            college.current_students = F('current_students') - 1
            college.save(update_fields=['current_students'])
            college.refresh_from_db()
        
        # Delete the student
        student.delete()
        
        return self.success_response(
            data={
                'deleted_student': {
                    'id': student_id,
                    'name': student_name,
                    'email': student_email
                }
            },
            message=f"Student {student_name} deleted successfully."
        )
