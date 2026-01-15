from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StudentChallengeSubmissionViewSet,
    submit_mcq_set_question, submit_coding_question, run_code,
    get_task_submissions, reset_quiz_submissions,
    mark_content_complete, get_course_progress, get_content_progress_list
)
from .views_profile import (
    UserProfileViewSet, LeaderboardView, GlobalLeaderboardView,
    CollegeLeaderboardView, BadgeListView, UserBadgesView,
    ProgressStatsView, ActivityFeedView
)
from .dashboard_views import (
    coding_challenge_leaderboard, company_challenge_progress,
    user_dashboard_stats
)
from courses.views import EnrollmentViewSet

router = DefaultRouter()
router.register(r'submissions', StudentChallengeSubmissionViewSet, basename='student-submission')
router.register(r'profile', UserProfileViewSet, basename='user-profile')
router.register(r'enrollments', EnrollmentViewSet, basename='student-enrollment')

urlpatterns = [
    path('', include(router.urls)),

    # Code execution endpoint
    path('submissions/run/', run_code, name='run-code'),

    # Content Submission endpoints (videos, documents, MCQ Sets, coding)
    # OLD MCQ endpoint removed - use MCQ Sets instead
    path('tasks/<int:task_id>/submit-mcq-set/', submit_mcq_set_question, name='submit-mcq-set'),
    path('tasks/<int:task_id>/submit-coding/', submit_coding_question, name='submit-coding'),
    path('tasks/<int:task_id>/submissions/', get_task_submissions, name='get-task-submissions'),
    path('tasks/<int:task_id>/reset-quiz/', reset_quiz_submissions, name='reset-quiz'),

    # Content Progress Tracking (videos, documents, questions - NO PAGES)
    path('content/mark-complete/', mark_content_complete, name='mark-content-complete'),
    path('courses/<int:course_id>/progress/', get_course_progress, name='get-course-progress'),
    path('courses/<int:course_id>/content-progress/', get_content_progress_list, name='get-content-progress-list'),

    # Leaderboard endpoints
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('leaderboard/global/', GlobalLeaderboardView.as_view(), name='global-leaderboard'),
    path('leaderboard/college/<int:college_id>/', CollegeLeaderboardView.as_view(), name='college-leaderboard'),

    # Badge endpoints
    path('badges/', BadgeListView.as_view(), name='badge-list'),
    path('badges/user/<int:user_id>/', UserBadgesView.as_view(), name='user-badges'),

    # Stats and activity endpoints
    path('stats/progress/', ProgressStatsView.as_view(), name='progress-stats'),
    path('activity/feed/', ActivityFeedView.as_view(), name='activity-feed'),

    # Dashboard endpoints
    path('dashboard/leaderboard/', coding_challenge_leaderboard, name='coding-leaderboard'),
    path('dashboard/company-progress/', company_challenge_progress, name='company-progress'),
    path('dashboard/stats/', user_dashboard_stats, name='dashboard-stats'),
]
