from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .views import (
    CourseViewSet, SyllabusViewSet, TopicViewSet,
    TaskViewSet, EnrollmentViewSet, TaskSubmissionViewSet
)
from .views_task_content import (
    TaskDocumentViewSet, TaskVideoViewSet, TaskQuestionViewSet,
    TaskMCQSetViewSet,
    TaskRichTextPageViewSet, TaskTextBlockViewSet,
    TaskCodeBlockViewSet, TaskVideoBlockViewSet, TaskHighlightBlockViewSet
)
from .models import Enrollment
from .serializers import EnrollmentSerializer
# Content submission views moved to student app (student.views)
# Content progress tracking moved to student app (student.views)





# Direct enrollment endpoint as a function view
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def enrollment_list(request):
    """Get enrollments for current user"""
    print(f"\n[DEBUG] ENROLLMENT LIST CALLED - User: {request.user}")
    enrollments = Enrollment.objects.filter(student=request.user).select_related('course')
    print(f"[DEBUG] Found {enrollments.count()} enrollments")
    serializer = EnrollmentSerializer(enrollments, many=True, context={'request': request})
    print(f"[DEBUG] Serialized data: {len(serializer.data)} items\n")
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Enrollments retrieved successfully.'
    })

router = DefaultRouter()
# Core resources
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'syllabi', SyllabusViewSet, basename='syllabus')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'submissions', TaskSubmissionViewSet, basename='task-submission')

# Task content resources
router.register('task-documents', TaskDocumentViewSet, basename='task-document')
router.register('task-videos', TaskVideoViewSet, basename='task-video')
router.register('task-questions', TaskQuestionViewSet, basename='task-question')
router.register('task-mcq-sets', TaskMCQSetViewSet, basename='task-mcq-set')
router.register('task-richtext-pages', TaskRichTextPageViewSet, basename='task-richtext-page')
router.register('task-text-blocks', TaskTextBlockViewSet, basename='task-text-block')
router.register('task-code-blocks', TaskCodeBlockViewSet, basename='task-code-block')
router.register('task-video-blocks', TaskVideoBlockViewSet, basename='task-video-block')
router.register('task-highlight-blocks', TaskHighlightBlockViewSet, basename='task-highlight-block')

urlpatterns = [
    # Direct enrollment endpoint (bypasses router)
    path('enrollments/', enrollment_list, name='enrollment-list-direct'),

    # Include router URLs
    path('', include(router.urls)),

    # Content submission endpoints moved to student app URLs:
    # /api/student/tasks/<task_id>/submit-mcq/
    # /api/student/tasks/<task_id>/submit-coding/
    # /api/student/tasks/<task_id>/submissions/
    # /api/student/tasks/<task_id>/reset-quiz/

    # Content progress tracking moved to student app URLs:
    # /api/student/content/mark-complete/
    # /api/student/courses/<course_id>/progress/
    # /api/student/courses/<course_id>/content-progress/
]
