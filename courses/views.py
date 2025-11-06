from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import models
from django.db.models import Q, F, Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import (
    Course, Syllabus, SyllabusTopic, Topic, Task, Enrollment, TaskSubmission,
    TaskRichTextPage, TaskTextBlock, TaskCodeBlock, TaskVideoBlock
)
from .serializers import (
    CourseListSerializer, CourseDetailSerializer, CourseCreateUpdateSerializer,
    SyllabusSerializer, SyllabusTopicSerializer, TaskDetailSerializer, TopicSerializer, TaskSerializer,
    EnrollmentSerializer, TaskSubmissionSerializer, TaskSubmissionGradeSerializer,
    TaskRichTextPageSerializer, TaskTextBlockSerializer, TaskCodeBlockSerializer,
    TaskVideoBlockSerializer
)
from api.utils import StandardResponseMixin, CustomPagination
from api.permissions import IsOwnerOrReadOnly, IsAdminUserOrReadOnly, IsStaffOrReadOnly


class CourseViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """ViewSet for managing courses"""
    queryset = Course.objects.all()
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['course_id', 'title', 'description']
    ordering_fields = ['title', 'created_at', 'difficulty_level']
    ordering = ['-created_at']
    pagination_class = CustomPagination
    lookup_field = 'id'

    @extend_schema(tags=['Courses'])

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return CourseCreateUpdateSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # College-specific filtering
        from django.db.models import Q
        
        if hasattr(user, 'college') and user.college:
            # Check if this is a college admin (CollegeUser from college authentication)
            # CollegeUser is a fake class created in college/authentication.py
            if user.__class__.__name__ == 'CollegeUser':
                # This is a college admin - show only their college's courses
                queryset = queryset.filter(college=user.college)
            # If user is a regular staff member, show their college's courses + admin courses
            elif user.is_staff and not user.is_superuser:
                queryset = queryset.filter(
                    Q(college=user.college) |                      # Their college's courses
                    Q(college__isnull=True)                        # Admin courses (no college assigned)
                )
            # For students (CustomUser with college but not staff), show college + admin courses
            else:
                queryset = queryset.filter(
                    Q(college=user.college, status='published') |  # Their college's published courses
                    Q(college__isnull=True, status='published')    # Admin courses (no college assigned)
                )
        # Superusers see all courses
        elif user.is_superuser:
            # Superusers see all courses (no filtering)
            pass
        else:
            # Non-college users or unauthenticated - show only published courses
            queryset = queryset.filter(status='published')

        # Filter by status (for admins)
        status_filter = self.request.query_params.get('status')
        if status_filter and (user.is_staff or user.is_superuser):
            queryset = queryset.filter(status=status_filter)

        # Filter by difficulty
        difficulty = self.request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)

        # Filter by featured
        is_featured = self.request.query_params.get('is_featured')
        if is_featured == 'true':
            queryset = queryset.filter(is_featured=True)

        # Filter by college (for superusers)
        college_id = self.request.query_params.get('college')
        if college_id and user.is_superuser:
            queryset = queryset.filter(college_id=college_id)

        return queryset.select_related('created_by', 'college')

    def perform_create(self, serializer):
        user = self.request.user
        # Handle college authentication (CollegeUser objects)
        if hasattr(user, 'college') and user.college and hasattr(user, 'college_id'):
            # This is a college admin - don't set created_by (CollegeUser), just set college
            serializer.save(college=user.college)
        elif hasattr(user, 'college') and user.college and not user.is_superuser:
            # This is a regular user with college - set both created_by and college
            serializer.save(created_by=user, college=user.college)
        else:
            # Superusers can manually assign college via the form
            serializer.save(created_by=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Course created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Course updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="Course deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Course retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Courses retrieved successfully."
        )

    @action(detail=True, methods=['post'])
    def enroll(self, request, id=None):
        """Enroll current user in the course"""
        course = self.get_object()

        if Enrollment.objects.filter(student=request.user, course=course).exists():
            return self.error_response(
                message="You are already enrolled in this course",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        enrollment = Enrollment.objects.create(
            student=request.user,
            course=course,
            status='enrolled'
        )

        course.current_enrollments += 1
        course.save()

        return self.success_response(
            data=EnrollmentSerializer(enrollment).data,
            message="Successfully enrolled in course",
            status_code=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def syllabi(self, request, id=None):
        """Get all syllabi for the course"""
        course = self.get_object()
        syllabi = course.syllabi.filter(is_published=True)
        serializer = SyllabusSerializer(syllabi, many=True)
        return self.success_response(
            data=serializer.data,
            message="Syllabi retrieved successfully."
        )

    @action(detail=True, methods=['get'])
    def tasks(self, request, id=None):
        """Get all tasks for the course"""
        course = self.get_object()
        tasks = course.tasks.filter(status='active')
        serializer = TaskSerializer(tasks, many=True)
        return self.success_response(
            data=serializer.data,
            message="Tasks retrieved successfully."
        )

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured courses"""
        courses = self.get_queryset().filter(is_featured=True, status='published')[:10]
        serializer = CourseListSerializer(courses, many=True)
        return self.success_response(
            data=serializer.data,
            message="Featured courses retrieved successfully."
        )

    @action(detail=False, methods=['get'])
    def my_courses(self, request):
        """Get courses the current user is enrolled in"""
        enrollments = Enrollment.objects.filter(student=request.user).select_related('course')
        courses = [enrollment.course for enrollment in enrollments]
        serializer = CourseListSerializer(courses, many=True)
        return self.success_response(
            data=serializer.data,
            message="Your courses retrieved successfully."
        )


class SyllabusViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """ViewSet for managing syllabi"""
    queryset = Syllabus.objects.all()
    serializer_class = SyllabusSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'created_at']
    ordering = ['order']
    pagination_class = CustomPagination

    @extend_schema(tags=['Course Syllabi'])

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        print(f"🔍 SyllabusViewSet - User: {user}, is_superuser: {user.is_superuser}")
        print(f"🔍 User college: {getattr(user, 'college', None)}")

        # College-specific filtering for syllabi
        if hasattr(user, 'college') and user.college:
            print(f"✅ User has college: {user.college}")
            print(f"🔍 User class name: {user.__class__.__name__}")

            # Check if this is actually a college admin (from college authentication)
            # College admins have __class__.__name__ == 'CollegeUser' (fake user from college app)
            is_college_admin = user.__class__.__name__ == 'CollegeUser'

            if is_college_admin:
                # College admin - show only their college's syllabi
                print("🏢 Filtering for college admin")
                queryset = queryset.filter(course__college=user.college)
            elif not user.is_superuser:
                # Regular students - show their college's syllabi + admin syllabi + enrolled courses
                print("👤 Filtering for regular student")
                from django.db.models import Q
                queryset = queryset.filter(
                    Q(course__college=user.college) |
                    Q(course__college__isnull=True) |
                    Q(course__enrollments__student=user)  # Show syllabi for enrolled courses
                )
                print(f"📊 Queryset count after filter: {queryset.count()}")
        else:
            print("⚠️ User has no college")

        course_id = self.request.query_params.get('course')
        if course_id:
            print(f"🎯 Filtering by course_id: {course_id}")
            queryset = queryset.filter(course_id=course_id)
            print(f"📊 Final queryset count: {queryset.count()}")

        return queryset.select_related('course').distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="Syllabus created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="Syllabus updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="Syllabus deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Syllabus retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Syllabi retrieved successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def reorder_topics(self, request, pk=None):
        """Reorder topics within a syllabus"""
        syllabus = self.get_object()
        topics_order = request.data.get('topics_order', [])

        if not isinstance(topics_order, list):
            return self.error_response(
                message="topics_order must be a list of objects with syllabus_topic_id and order",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            for item in topics_order:
                syllabus_topic_id = item.get('syllabus_topic_id')
                new_order = item.get('order')

                if syllabus_topic_id is not None and new_order is not None:
                    SyllabusTopic.objects.filter(
                        id=syllabus_topic_id,
                        syllabus=syllabus
                    ).update(order=new_order)

            return self.success_response(
                message="Topics reordered successfully."
            )
        except Exception as e:
            return self.error_response(
                message=f"Failed to reorder topics: {str(e)}",
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def add_topic(self, request, pk=None):
        """Add a topic to the syllabus"""
        syllabus = self.get_object()
        topic_id = request.data.get('topic_id')

        if not topic_id:
            return self.error_response(
                message="topic_id is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            topic = Topic.objects.get(id=topic_id)

            # Check if topic is already in syllabus
            if SyllabusTopic.objects.filter(syllabus=syllabus, topic=topic).exists():
                return self.error_response(
                    message="Topic is already in this syllabus",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Get max order
            max_order = SyllabusTopic.objects.filter(syllabus=syllabus).aggregate(
                max_order=models.Max('order')
            )['max_order'] or -1

            # Create SyllabusTopic
            syllabus_topic = SyllabusTopic.objects.create(
                syllabus=syllabus,
                topic=topic,
                order=max_order + 1
            )

            return self.success_response(
                data=SyllabusTopicSerializer(syllabus_topic).data,
                message="Topic added to syllabus successfully.",
                status_code=status.HTTP_201_CREATED
            )
        except Topic.DoesNotExist:
            return self.error_response(
                message="Topic not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return self.error_response(
                message=f"Failed to add topic: {str(e)}",
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['delete'], permission_classes=[IsStaffOrReadOnly])
    def remove_topic(self, request, pk=None):
        """Remove a topic from the syllabus"""
        syllabus = self.get_object()
        syllabus_topic_id = request.data.get('syllabus_topic_id')

        if not syllabus_topic_id:
            return self.error_response(
                message="syllabus_topic_id is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            syllabus_topic = SyllabusTopic.objects.get(
                id=syllabus_topic_id,
                syllabus=syllabus
            )
            syllabus_topic.delete()

            return self.success_response(
                message="Topic removed from syllabus successfully.",
                status_code=status.HTTP_204_NO_CONTENT
            )
        except SyllabusTopic.DoesNotExist:
            return self.error_response(
                message="SyllabusTopic not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return self.error_response(
                message=f"Failed to remove topic: {str(e)}",
                status_code=status.HTTP_400_BAD_REQUEST
            )


class TopicViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """ViewSet for managing topics"""
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['title', 'created_at']
    ordering = ['title']
    pagination_class = CustomPagination

    @extend_schema(tags=['Course Topics'])

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # College-specific filtering for topics
        if hasattr(user, 'college') and user.college:
            is_college_admin = user.__class__.__name__ == 'CollegeUser'

            if is_college_admin:
                # College admin - show only their college's topics
                queryset = queryset.filter(course__college=user.college)
            elif not user.is_superuser:
                # Regular students - show their college's topics + admin topics + enrolled courses
                from django.db.models import Q
                queryset = queryset.filter(
                    Q(course__college=user.college) |
                    Q(course__college__isnull=True) |
                    Q(course__enrollments__student=user)  # Show topics for enrolled courses
                )

        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        return queryset.select_related('course').distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="Topic created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="Topic updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="Topic deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Topic retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Topics retrieved successfully."
        )
import logging
logger = logging.getLogger(__name__)

class TaskViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """
    ViewSet for managing tasks.
    - List/Retrieve: Uses nested serializers for content.
    - Safe filters: Handles invalid params without 500 errors.
    """
    queryset = Task.objects.all()
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['order', 'due_date', 'created_at']
    ordering = ['order']
    pagination_class = CustomPagination

    @extend_schema(tags=['Course Tasks & Assignments'])
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        query_params = self.request.query_params
        
        # College-specific filtering for tasks
        if hasattr(user, 'college') and user.college:
            is_college_admin = user.__class__.__name__ == 'CollegeUser'

            if is_college_admin:
                # College admin - show only their college's tasks
                queryset = queryset.filter(topic__course__college=user.college)
            elif not user.is_superuser:
                # Regular students - show their college's tasks + admin tasks + enrolled courses
                from django.db.models import Q
                queryset = queryset.filter(
                    Q(topic__course__college=user.college) |
                    Q(topic__course__college__isnull=True) |
                    Q(topic__course__enrollments__student=user)  # Show tasks for enrolled courses
                )

        # --- Validate and filter topic ---
        topic_id = query_params.get('topic')
        if topic_id:
            try:
                # Validate integer ID
                topic_id = int(topic_id)
                queryset = queryset.filter(topic_id=topic_id)
            except ValueError as e:
                logger.warning(f"Invalid topic_id format: {topic_id} - {str(e)}")
                # Return empty queryset for invalid ID instead of raising error
                return queryset.none()
            except Exception as e:
                logger.error(f"Topic filter error: {str(e)}")
                return queryset.none()

        # --- Course filter (similar validation) ---
        course_id = query_params.get('course')
        if course_id:
            try:
                # Validate integer ID
                course_id = int(course_id)
                queryset = queryset.filter(course_id=course_id)
            except ValueError as e:
                logger.warning(f"Invalid course_id: {course_id} - {str(e)}")
                return queryset.none()
            except Exception as e:
                logger.error(f"Course filter error: {str(e)}")
                return queryset.none()

        # Other filters (safe)
        task_type = query_params.get('task_type')
        if task_type:
            queryset = queryset.filter(task_type=task_type)

        task_status = query_params.get('status')
        if task_status:
            queryset = queryset.filter(status=task_status)

        # Prefetch related to avoid null errors in serializer
        queryset = queryset.select_related('course', 'topic', 'created_by').prefetch_related(
            'documents', 'videos', 'questions', 'richtext_pages'
        ).filter(status='active')

        return queryset.distinct()

    def get_serializer_class(self):
        """
        Switch serializers:
        - retrieve: TaskDetailSerializer (nested content: documents, videos, etc.)
        - list: TaskSerializer (lightweight)
        - create/update: TaskSerializer (or add a dedicated one if needed)
        """
        if self.action == 'retrieve':
            return TaskDetailSerializer
        return TaskSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # --- CRUD Overrides with Standard Responses ---
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=TaskSerializer(serializer.instance).data,
            message="Task created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=TaskSerializer(serializer.instance).data,
            message="Task updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="Task deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Task retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return self.success_response(
                data=serializer.data,
                message="Tasks retrieved successfully."
            )
        except Exception as e:
            logger.error(f"Task list error: {str(e)}")
            return self.error_response(
                message="Invalid query parameters or server error",
                status_code=status.HTTP_400_BAD_REQUEST
            )

    # --- Custom Actions ---
    @action(detail=True, methods=['get'])
    def submissions(self, request, pk=None):
        """Get all submissions for a task"""
        task = self.get_object()
        submissions = task.submissions.all()  # Assumes related_name='submissions' on TaskSubmission.task
        serializer = TaskSubmissionSerializer(submissions, many=True)
        return self.success_response(
            data=serializer.data,
            message="Submissions retrieved successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def content_complete(self, request, pk=None):
        """
        Mark specific content (page/video/document) as completed.
        Uses ContentSubmission model for tracking.
        """
        from .models import ContentSubmission, TaskDocument, TaskVideo, TaskRichTextPage
        from django.shortcuts import get_object_or_404
        
        task = self.get_object()
        
        # Accept both snake_case and camelCase for frontend compatibility
        content_id = request.data.get('content_id') or request.data.get('contentId')
        content_type = request.data.get('content_type') or request.data.get('contentType')

        # Debug logging
        logger.info(f"Content complete request - Task: {task.id}, User: {request.user.email}")
        logger.info(f"Request data: {request.data}")
        logger.info(f"Parsed - content_id: {content_id}, content_type: {content_type}")

        if not content_id or not content_type:
            logger.warning(f"Missing required fields. content_id: {content_id}, content_type: {content_type}, data: {request.data}")
            return self.error_response(
                message=f"content_id and content_type are required. Received data: {dict(request.data)}",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Check enrollment
            if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
                return self.error_response(
                    message="You are not enrolled in this course",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Create submission based on content type
            if content_type == 'document':
                content_obj = get_object_or_404(TaskDocument, id=content_id, task=task)
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    document=content_obj,
                    defaults={
                        'task': task,
                        'submission_type': 'document',
                        'completed': True
                    }
                )
            elif content_type == 'video':
                content_obj = get_object_or_404(TaskVideo, id=content_id, task=task)
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    video=content_obj,
                    defaults={
                        'task': task,
                        'submission_type': 'video',
                        'completed': True
                    }
                )
            elif content_type == 'page':
                content_obj = get_object_or_404(TaskRichTextPage, id=content_id, task=task)
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    page=content_obj,
                    defaults={
                        'task': task,
                        'submission_type': 'page',
                        'completed': True
                    }
                )
            else:
                return self.error_response(
                    message="Invalid content_type. Must be 'document', 'video', or 'page'",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            return self.success_response(
                data={
                    'content_type': content_type,
                    'content_id': content_id,
                    'completed': True,
                    'submitted_at': submission.submitted_at.isoformat()
                },
                message=f"{content_type.capitalize()} marked as completed."
            )
        except Exception as e:
            logger.error(f"Content complete error: {str(e)}")
            return self.error_response(
                message=f"Failed to mark complete: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnrollmentViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """ViewSet for managing enrollments"""
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['enrolled_at', 'progress_percentage']
    ordering = ['-enrolled_at']
    pagination_class = CustomPagination

    @extend_schema(tags=['Course Enrollments'])

    def get_queryset(self):
        queryset = super().get_queryset()

        # Students can only see their own enrollments
        if not self.request.user.is_staff:
            queryset = queryset.filter(student=self.request.user)

        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        enrollment_status = self.request.query_params.get('status')
        if enrollment_status:
            queryset = queryset.filter(status=enrollment_status)

        return queryset.select_related('student', 'course')

    def perform_create(self, serializer):
        serializer.save(student=self.request.user)

    def create(self, request, *args, **kwargs):
        user = request.user

        # Check if user is approved
        if user.approval_status != 'approved':
            return self.error_response(
                message="Your account must be approved before enrolling in courses.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Check if user is verified
        if not user.is_verified:
            return self.error_response(
                message="Your account is not verified yet. Please verify your account to enroll in courses.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Check if college is active
        if user.college and not user.college.is_active:
            return self.error_response(
                message="Your college is currently inactive. Please contact support for more information.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Increment course enrollment count
        course = serializer.instance.course
        course.current_enrollments += 1
        course.save()

        # Update UserProfile courses_enrolled counter
        from student.user_profile_models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.courses_enrolled += 1
        profile.save(update_fields=['courses_enrolled'])

        return self.success_response(
            data=serializer.data,
            message="Enrollment created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="Enrollment updated successfully."
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Enrollment retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Enrollments retrieved successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        """Mark an enrollment as completed"""
        enrollment = self.get_object()
        
        # Check if user owns this enrollment or is staff
        if not request.user.is_staff and enrollment.student != request.user:
            return self.error_response(
                message="You do not have permission to complete this enrollment.",
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        # Check if it was already completed
        was_completed_before = enrollment.status == 'completed'

        # Recalculate progress first to ensure it's accurate
        enrollment.calculate_progress()

        # If progress is not 100%, set it to 100% and mark as completed
        if enrollment.progress_percentage < 100:
            enrollment.progress_percentage = 100.00

        enrollment.status = 'completed'
        if not enrollment.completed_at:
            enrollment.completed_at = timezone.now()

            # Update UserProfile courses_completed counter
            if not was_completed_before:
                from student.user_profile_models import UserProfile
                profile, created = UserProfile.objects.get_or_create(user=enrollment.student)
                profile.courses_completed += 1
                profile.save(update_fields=['courses_completed'])

        enrollment.save(update_fields=['status', 'progress_percentage', 'completed_at'])

        serializer = self.get_serializer(enrollment)
        return self.success_response(
            data=serializer.data,
            message="Enrollment marked as completed successfully."
        )


class TaskSubmissionViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """ViewSet for managing task submissions"""
    queryset = TaskSubmission.objects.all()
    serializer_class = TaskSubmissionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['submitted_at', 'score']
    ordering = ['-submitted_at']
    pagination_class = CustomPagination

    @extend_schema(tags=['Task Submissions'])

    def get_queryset(self):
        queryset = super().get_queryset()

        # Students can only see their own submissions
        if not self.request.user.is_staff:
            queryset = queryset.filter(student=self.request.user)

        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)

        submission_status = self.request.query_params.get('status')
        if submission_status:
            queryset = queryset.filter(status=submission_status)

        return queryset.select_related('task', 'student', 'graded_by')

    def perform_create(self, serializer):
        serializer.save(student=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="Submission created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="Submission updated successfully."
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Submission retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Submissions retrieved successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """Submit the task (change status from draft to submitted)"""
        submission = self.get_object()

        if submission.student != request.user:
            return self.error_response(
                message="You can only submit your own submissions",
                status_code=status.HTTP_403_FORBIDDEN
            )

        if submission.status != 'draft':
            return self.error_response(
                message="Only draft submissions can be submitted",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        submission.status = 'submitted'
        submission.submitted_at = timezone.now()
        submission.save()

        return self.success_response(
            data=TaskSubmissionSerializer(submission).data,
            message="Submission submitted successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def grade(self, request, pk=None):
        """Grade a submission (staff only)"""
        if not request.user.is_staff:
            return self.error_response(
                message="Only staff members can grade submissions",
                status_code=status.HTTP_403_FORBIDDEN
            )

        submission = self.get_object()
        serializer = TaskSubmissionGradeSerializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(graded_by=request.user, graded_at=timezone.now())

        return self.success_response(
            data=TaskSubmissionSerializer(submission).data,
            message="Submission graded successfully."
        )
