from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CertificationAdminViewSet,
    CertificationQuestionAdminViewSet,
    StudentCertificationViewSet,
    StudentCertificationAttemptViewSet,
    download_certificate_view,
    QuestionBankViewSet,
    QuestionBankCategoryViewSet,
    CertificationQuestionBankViewSet,
    AIProviderSettingsViewSet,
    AIGenerationLogViewSet,
)

# Admin router for certification management (staff/superuser only)
admin_router = DefaultRouter()
admin_router.register(
    r'certifications',
    CertificationAdminViewSet,
    basename='admin-certification'
)
admin_router.register(
    r'questions',
    CertificationQuestionAdminViewSet,
    basename='admin-question'
)

# Question Bank router (admin only)
question_bank_router = DefaultRouter()
question_bank_router.register(
    r'questions',
    QuestionBankViewSet,
    basename='question-bank'
)
question_bank_router.register(
    r'categories',
    QuestionBankCategoryViewSet,
    basename='question-category'
)
question_bank_router.register(
    r'certification-questions',
    CertificationQuestionBankViewSet,
    basename='certification-question-bank'
)
question_bank_router.register(
    r'ai-settings',
    AIProviderSettingsViewSet,
    basename='ai-settings'
)
question_bank_router.register(
    r'ai-logs',
    AIGenerationLogViewSet,
    basename='ai-logs'
)

# Student router for taking certifications
student_router = DefaultRouter()
student_router.register(
    r'certifications',
    StudentCertificationViewSet,
    basename='student-certification'
)
student_router.register(
    r'attempts',
    StudentCertificationAttemptViewSet,
    basename='student-attempt'
)

urlpatterns = [
    # Admin certification routes
    path('admin/cert/', include(admin_router.urls)),

    # Question Bank routes (admin only)
    path('admin/question-bank/', include(question_bank_router.urls)),

    # Student certification routes
    path('student/certifications/', include(student_router.urls)),

    # Standalone certificate download endpoint (bypasses DRF rendering)
    path('student/certifications/attempts/<int:attempt_id>/download_certificate/',
         download_certificate_view,
         name='download-certificate'),
]
