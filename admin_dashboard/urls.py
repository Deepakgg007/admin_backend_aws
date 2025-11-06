from django.urls import path
from .views import (
    AdminDashboardAnalyticsView,
    StudentDashboardView,
    CourseCompletionReportView,
    StudentsReportView,
    StudentDeleteView
)

urlpatterns = [
    path("analytics/", AdminDashboardAnalyticsView.as_view(), name="dashboard-analytics"),
    path("student/", StudentDashboardView.as_view(), name="student-dashboard"),
    path("completion-report/", CourseCompletionReportView.as_view(), name="completion-report"),
    path("students-report/", StudentsReportView.as_view(), name="students-report"),
    path("students/<int:student_id>/delete/", StudentDeleteView.as_view(), name="delete-student"),
]
