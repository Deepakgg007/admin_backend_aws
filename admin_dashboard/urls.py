from django.urls import path
from .views import (
    AdminDashboardAnalyticsView,
    StudentDashboardView,
    CourseCompletionReportView,
    StudentsReportView,
    StudentSubmissionStatsView,
    StudentDeleteView,
    PendingOtherCollegeStudentsView,
    OtherCollegeStudentActionView
)

urlpatterns = [
    path("analytics/", AdminDashboardAnalyticsView.as_view(), name="dashboard-analytics"),
    path("student/", StudentDashboardView.as_view(), name="student-dashboard"),
    path("completion-report/", CourseCompletionReportView.as_view(), name="completion-report"),
    path("students-report/", StudentsReportView.as_view(), name="students-report"),
    path("students/<int:student_id>/submissions/", StudentSubmissionStatsView.as_view(), name="student-submissions"),
    path("students/<int:student_id>/delete/", StudentDeleteView.as_view(), name="delete-student"),
    # Other college student approval endpoints
    path("other-college-students/pending/", PendingOtherCollegeStudentsView.as_view(), name="pending-other-college-students"),
    path("other-college-students/<int:student_id>/action/", OtherCollegeStudentActionView.as_view(), name="other-college-student-action"),
]
