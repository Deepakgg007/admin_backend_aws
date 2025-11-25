"""
College App URLs
All college-related endpoints organized here
"""
from django.urls import path
from .views import (
    CollegeLoginView,
    PendingStudentsView,
    StudentApprovalActionView,
    StudentDeleteView,
    CollegeStudentCountView,
    CollegeForgotPasswordRequestView,
    CollegeVerifyOTPView,
    CollegeResetPasswordView,
    EnrolledStudentsListView,
    EngagementStatsView
)

app_name = 'college'

urlpatterns = [
    # College Authentication
    path('login/', CollegeLoginView.as_view(), name='login'),

    # College Password Reset
    path('forgot-password/', CollegeForgotPasswordRequestView.as_view(), name='college-forgot-password'),
    path('verify-otp/', CollegeVerifyOTPView.as_view(), name='college-verify-otp'),
    path('reset-password/', CollegeResetPasswordView.as_view(), name='college-reset-password'),

    # Student Approval Management
    path('students/pending/', PendingStudentsView.as_view(), name='pending-students'),
    path('students/<int:student_id>/action/', StudentApprovalActionView.as_view(), name='student-action'),
    path('students/<int:student_id>/delete/', StudentDeleteView.as_view(), name='delete-student'),
    path('students/count/', CollegeStudentCountView.as_view(), name='student-count'),

    # Enrolled Students Management
    path('students/enrolled/', EnrolledStudentsListView.as_view(), name='enrolled-students'),

    # Engagement Statistics
    path('engagement-stats/', EngagementStatsView.as_view(), name='engagement-stats'),
]
