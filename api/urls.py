from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)
from .views import (
    api_root,
    UniversityViewSet, OrganizationViewSet, CollegeViewSet
)
from courses.views import (
    CourseViewSet, SyllabusViewSet, TopicViewSet,
    TaskViewSet, EnrollmentViewSet, TaskSubmissionViewSet
)
from courses.views_task_content import (
    TaskDocumentViewSet, TaskVideoViewSet, TaskQuestionViewSet,
    TaskRichTextPageViewSet, TaskTextBlockViewSet,
    TaskCodeBlockViewSet, TaskVideoBlockViewSet
)
from coding.views import (
    ChallengeViewSet, StarterCodeViewSet, TestCaseViewSet
)
from company.views import (
    CompanyViewSet, ConceptViewSet, ConceptChallengeViewSet, JobViewSet
)



from course_cert.views import (
    CertificationAdminViewSet,
    CertificationQuestionAdminViewSet,
    StudentCertificationViewSet,
    StudentCertificationAttemptViewSet,
    
)
from course_cert.views_college_certifications import (
    CollegeCertificationViewSet,

    
)



router = DefaultRouter()
router.register('universities', UniversityViewSet, basename='university')
router.register('organizations', OrganizationViewSet, basename='organization')
router.register('colleges', CollegeViewSet, basename='college')

# Courses app viewsets
router.register('courses', CourseViewSet, basename='course')
router.register('syllabi', SyllabusViewSet, basename='syllabus')
router.register('topics', TopicViewSet, basename='topic')
router.register('tasks', TaskViewSet, basename='task')
router.register('enrollments', EnrollmentViewSet, basename='enrollment')
router.register('submissions', TaskSubmissionViewSet, basename='task-submission')

# Task content viewsets
router.register('task-documents', TaskDocumentViewSet, basename='task-document')
router.register('task-videos', TaskVideoViewSet, basename='task-video')
router.register('task-questions', TaskQuestionViewSet, basename='task-question')
router.register('task-richtext-pages', TaskRichTextPageViewSet, basename='task-richtext-page')
router.register('task-text-blocks', TaskTextBlockViewSet, basename='task-text-block')
router.register('task-code-blocks', TaskCodeBlockViewSet, basename='task-code-block')
router.register('task-video-blocks', TaskVideoBlockViewSet, basename='task-video-block')

# Coding challenges viewsets
router.register('challenges', ChallengeViewSet, basename='challenge')
router.register('starter-codes', StarterCodeViewSet, basename='starter-code')
router.register('test-cases', TestCaseViewSet, basename='test-case')

# Company viewsets
router.register('companies', CompanyViewSet, basename='company')
router.register('concepts', ConceptViewSet, basename='concept')
router.register('concept-challenges', ConceptChallengeViewSet, basename='concept-challenge')
router.register('jobs', JobViewSet, basename='job')


# Admin router for certification management (staff/superuser only)
admin_cert_router = DefaultRouter()
admin_cert_router.register(
    r'certifications',
    CertificationAdminViewSet,
    basename='admin-certification'
)
admin_cert_router.register(
    r'questions',
    CertificationQuestionAdminViewSet,
    basename='admin-question'
)

# Student router for taking certifications
student_cert_router = DefaultRouter()
student_cert_router.register(
    r'certifications',
    StudentCertificationViewSet,
    basename='student-certification'
)
student_cert_router.register(
    r'attempts',
    StudentCertificationAttemptViewSet,
    basename='student-attempt'
)
router.register(r"college/certifications", CollegeCertificationViewSet, basename="college-certifications")



urlpatterns = [
    path('', api_root, name='api-root'),

    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Router URLs
    path('', include(router.urls)),
    
    # Admin certification routes
    path('admin/cert/', include(admin_cert_router.urls)),
    
    # Student certification routes
    path('student/certifications/', include(student_cert_router.urls)),
]

