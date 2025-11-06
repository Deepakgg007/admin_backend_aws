from rest_framework import serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from .models import (
    Course, Syllabus, SyllabusTopic, Topic, Task, Enrollment, TaskSubmission,
    TaskDocument, TaskVideo, TaskQuestion, TaskMCQ, TaskCoding, TaskTestCase,
    TaskRichTextPage, TaskTextBlock, TaskCodeBlock, TaskVideoBlock
)
# ContentSubmission moved to student app
from student.models import ContentSubmission

User = get_user_model()


class CourseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing courses"""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    creator_type = serializers.SerializerMethodField()
    college_name = serializers.CharField(source='college.name', read_only=True)
    thumbnail = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True, use_url=True)
    intro_video = serializers.FileField(required=False, allow_null=True, allow_empty_file=True, use_url=True)

    class Meta:
        model = Course
        fields = [
            'id', 'uuid_id', 'course_id', 'title', 'slug', 'description',
            'difficulty_level', 'duration_hours', 'status', 'thumbnail',
            'intro_video', 'video_intro_url',
            'is_featured', 'current_enrollments', 'created_by_name', 'creator_type', 'college', 'college_name', 'created_at'
        ]

    def get_creator_type(self, obj):
        """Determine the type of creator"""
        if not obj.created_by:
            # If no created_by but has college, it's a college admin
            if obj.college:
                return 'College'
            return 'System'

        if obj.created_by.is_superuser:
            return 'Superuser'
        elif hasattr(obj.created_by, 'college') and obj.created_by.college:
            # Check if this user is staff for their college
            if obj.created_by.is_staff:
                return 'College'
            return 'Student'
        return 'User'


class TopicSerializer(serializers.ModelSerializer):
    """Serializer for topics"""
    course_title = serializers.CharField(source='course.title', read_only=True)
    creator_type = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = [
            'id', 'topic_id', 'course', 'course_title', 'title', 'description',
            'is_preview', 'is_published', 'creator_type', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'topic_id', 'created_at', 'updated_at']

    def get_creator_type(self, obj):
        """Derive creator type from the associated course"""
        if not obj.course or not obj.course.created_by:
            if obj.course and obj.course.college:
                return 'College'
            return 'System'

        creator = obj.course.created_by
        if creator.is_superuser:
            return 'Superuser'
        elif hasattr(creator, 'college') and creator.college:
            if creator.is_staff:
                return 'College'
            return 'Student'
        return 'User'


class SyllabusTopicSerializer(serializers.ModelSerializer):
    """Serializer for SyllabusTopic through model"""
    topic_id = serializers.IntegerField(source='topic.id', read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    topic_description = serializers.CharField(source='topic.description', read_only=True)

    class Meta:
        model = SyllabusTopic
        fields = ['id', 'syllabus', 'topic', 'topic_id', 'topic_title', 'topic_description', 'order']
        read_only_fields = ['id']


class SyllabusSerializer(serializers.ModelSerializer):
    """Serializer for syllabus with nested topics"""
    topics_count = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    ordered_topics = serializers.SerializerMethodField()
    creator_type = serializers.SerializerMethodField()

    class Meta:
        model = Syllabus
        fields = [
            'id', 'syllabus_id', 'course', 'course_title', 'title', 'description',
            'order', 'is_published', 'creator_type',
            'topics_count', 'ordered_topics', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'syllabus_id', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_topics_count(self, obj):
        return SyllabusTopic.objects.filter(syllabus=obj).count()

    def get_creator_type(self, obj):
        """Derive creator type from the associated course"""
        if not obj.course or not obj.course.created_by:
            if obj.course and obj.course.college:
                return 'College'
            return 'System'

        creator = obj.course.created_by
        if creator.is_superuser:
            return 'Superuser'
        elif hasattr(creator, 'college') and creator.college:
            if creator.is_staff:
                return 'College'
            return 'Student'
        return 'User'

    @extend_schema_field(SyllabusTopicSerializer(many=True))
    def get_ordered_topics(self, obj):
        syllabus_topics = SyllabusTopic.objects.filter(syllabus=obj).select_related('topic').order_by('order')
        return SyllabusTopicSerializer(syllabus_topics, many=True).data


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for tasks"""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    creator_type = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True, allow_null=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'task_id', 'course', 'course_title', 'topic', 'topic_title',
            'title', 'description', 'task_type', 'status', 'instructions',
            'start_date', 'due_date', 'duration_minutes',
            'max_score', 'passing_score',
            'allow_late_submission', 'is_mandatory', 'order',
            'created_by', 'created_by_name', 'creator_type', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'task_id', 'created_by', 'created_at', 'updated_at']

    @extend_schema_field(serializers.BooleanField())
    def get_is_active(self, obj):
        return obj.is_active

    def get_creator_type(self, obj):
        """Determine the type of creator"""
        if not obj.created_by:
            # If no created_by but has course with college, it's a college admin
            if obj.course and obj.course.college:
                return 'College'
            return 'System'

        if obj.created_by.is_superuser:
            return 'Superuser'
        elif hasattr(obj.created_by, 'college') and obj.created_by.college:
            # Check if this user is staff for their college
            if obj.created_by.is_staff:
                return 'College'
            return 'Student'
        return 'User'


class CourseDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for course with all related data"""
    created_by = serializers.SerializerMethodField()
    college_info = serializers.SerializerMethodField()
    syllabi = SyllabusSerializer(many=True, read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)
    total_topics = serializers.SerializerMethodField()
    total_tasks = serializers.SerializerMethodField()
    thumbnail = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True, use_url=True)
    intro_video = serializers.FileField(required=False, allow_null=True, allow_empty_file=True, use_url=True)

    class Meta:
        model = Course
        fields = [
            'id', 'uuid_id', 'course_id', 'title', 'slug', 'description',
            'difficulty_level', 'duration_hours', 'status', 'thumbnail',
            'intro_video', 'video_intro_url', 'current_enrollments',
            'is_featured', 'created_by', 'college', 'college_info', 'syllabi', 'tasks',
            'total_topics', 'total_tasks', 'created_at', 'updated_at', 'published_at'
        ]
        read_only_fields = ['id', 'uuid_id', 'slug', 'current_enrollments', 'created_at', 'updated_at']

    def get_created_by(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'name': obj.created_by.get_full_name(),
                'email': obj.created_by.email
            }
        return None

    def get_college_info(self, obj):
        if obj.college:
            return {
                'id': obj.college.id,
                'name': obj.college.name,
                'code': getattr(obj.college, 'code', None)
            }
        return None

    def get_total_topics(self, obj):
        return Topic.objects.filter(course=obj, is_published=True).count()

    def get_total_tasks(self, obj):
        return obj.tasks.filter(status='active').count()


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating courses"""
    class Meta:
        model = Course
        fields = [
            'course_id', 'title', 'description', 'difficulty_level',
            'duration_hours', 'status', 'thumbnail', 'intro_video', 'video_intro_url',
            'is_featured', 'college', 'published_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only superusers can manually set college via form
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            # Remove college field for college admins (will be set automatically)
            # and regular users, but keep it for superusers
            if not user.is_superuser:
                self.fields.pop('college', None)


class EnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for enrollments with full course details"""
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_email = serializers.CharField(source='student.email', read_only=True)
    course = CourseDetailSerializer(read_only=True)
    course_id = serializers.IntegerField(write_only=True, required=False)
    completion_status = serializers.SerializerMethodField()
    completed_topics = serializers.SerializerMethodField()
    total_topics = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            'id', 'enrollment_id', 'student', 'student_name', 'student_email',
            'course', 'course_id', 'status', 'completion_status',
            'progress_percentage', 'completed_topics', 'total_topics',
            'enrolled_at', 'started_at', 'completed_at', 'last_accessed'
        ]
        read_only_fields = [
            'id', 'enrollment_id', 'student', 'enrolled_at',
            'student_name', 'student_email', 'completion_status',
            'completed_topics', 'total_topics'
        ]

    def get_completion_status(self, obj):
        """Calculate completion status"""
        if obj.completed_at:
            return 'completed'
        elif obj.progress_percentage >= 75:
            return 'almost_done'
        elif obj.progress_percentage >= 25:
            return 'in_progress'
        elif obj.started_at:
            return 'started'
        else:
            return 'not_started'

    def get_completed_topics(self, obj):
        """Get number of completed topics"""
        from .models import Topic, TaskSubmission
        # Get all topics for this course
        topics = Topic.objects.filter(course=obj.course)
        completed_count = 0
        
        for topic in topics:
            # Get all tasks in this topic
            tasks = topic.tasks.all()
            if tasks.exists():
                # Check if all tasks are completed
                all_completed = True
                for task in tasks:
                    # Check if user has completed this task
                    has_submission = TaskSubmission.objects.filter(
                        student=obj.student,
                        task=task,
                        status__in=['completed', 'graded']  # Both completed and graded
                    ).exists()
                    if not has_submission:
                        all_completed = False
                        break
                if all_completed:
                    completed_count += 1
        
        return completed_count

    def get_total_topics(self, obj):
        """Get total number of topics in course"""
        from .models import Topic
        return Topic.objects.filter(course=obj.course).count()

    def get_progress_percentage(self, obj):
        """Calculate and return progress percentage"""
        # Calculate progress on-the-fly
        obj.calculate_progress()
        return float(obj.progress_percentage)

    def validate(self, attrs):
        # Check if already enrolled
        request = self.context.get('request')
        course_id = attrs.get('course_id')
        
        if request and hasattr(request, 'user') and course_id:
            from .models import Course
            try:
                course = Course.objects.get(id=course_id)
                if Enrollment.objects.filter(student=request.user, course=course).exists():
                    raise serializers.ValidationError({
                        'course': 'You are already enrolled in this course'
                    })
                attrs['course'] = course
            except Course.DoesNotExist:
                raise serializers.ValidationError({
                    'course_id': 'Course not found'
                })

        return attrs

import json
import logging
from rest_framework import serializers
from django.utils import timezone  # For validation



logger = logging.getLogger(__name__)

# ============================================
# Mixin for Completion Check (Uses TaskSubmission JSON)
# ============================================
class CompletionCheckMixin:
    """Mixin to add is_completed check for content items using ContentSubmission model"""
    def _get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False

        student = request.user

        # Check ContentSubmission for all content types including pages
        content_type = self._get_content_type()

        try:
            if content_type == 'document':
                submission = ContentSubmission.objects.filter(
                    student=student,
                    document=obj,
                    completed=True
                ).exists()
            elif content_type == 'video':
                submission = ContentSubmission.objects.filter(
                    student=student,
                    video=obj,
                    completed=True
                ).exists()
            elif content_type == 'page':
                submission = ContentSubmission.objects.filter(
                    student=student,
                    page=obj,
                    completed=True
                ).exists()
            else:
                return False

            return submission
            
        except Exception as e:
            logger.error(f"Error checking completion: {e}")
            return False

    def _get_content_type(self):
        """Map serializer/model to content_type string."""
        model_name = self.Meta.model.__name__.lower()
        if 'document' in model_name:
            return 'document'
        if 'video' in model_name:
            return 'video'
        if 'page' in model_name or 'richtext' in model_name:
            return 'page'
        return ''  # Unknown

# ============================================
# Task Content Serializers (With is_completed)
# ============================================

class TaskDocumentSerializer(serializers.ModelSerializer, CompletionCheckMixin):
    """Serializer for task documents"""
    document_url = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()  # Added

    class Meta:
        model = TaskDocument
        fields = [
            'id', 'document_id', 'task', 'title', 'document', 'document_url',
            'description', 'order', 'uploaded_at', 'updated_at', 'is_completed'
        ]
        read_only_fields = ['id', 'document_id', 'uploaded_at', 'updated_at', 'is_completed']

    def get_document_url(self, obj):
        if obj.document:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document.url)
            return obj.document.url
        return None

    def get_is_completed(self, obj):
        return self._get_is_completed(obj)


class TaskVideoSerializer(serializers.ModelSerializer, CompletionCheckMixin):
    """Serializer for task videos"""
    video_url = serializers.SerializerMethodField()
    youtube_embed_id = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()  # Added

    class Meta:
        model = TaskVideo
        fields = [
            'id', 'video_id', 'task', 'title', 'video_file', 'video_url',
            'youtube_url', 'youtube_embed_id', 'description', 'order',
            'uploaded_at', 'updated_at', 'is_completed'
        ]
        read_only_fields = ['id', 'video_id', 'uploaded_at', 'updated_at', 'is_completed']

    def get_video_url(self, obj):
        if obj.video_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
            return obj.video_file.url
        return None

    def get_youtube_embed_id(self, obj):
        return obj.get_youtube_embed_id() if hasattr(obj, 'get_youtube_embed_id') else None

    def get_is_completed(self, obj):
        return self._get_is_completed(obj)

    def validate(self, attrs):
        # Skip validation for partial updates (PATCH) when only updating other fields like 'order'
        if self.partial and 'video_file' not in attrs and 'youtube_url' not in attrs:
            return attrs

        # For full updates or when video fields are being updated
        video_file = attrs.get('video_file')
        youtube_url = attrs.get('youtube_url')

        # If this is an update and we're not changing video fields, check the instance
        if self.instance:
            video_file = video_file if 'video_file' in attrs else self.instance.video_file
            youtube_url = youtube_url if 'youtube_url' in attrs else self.instance.youtube_url

        if not video_file and not youtube_url:
            raise serializers.ValidationError(
                'Either video_file or youtube_url must be provided'
            )

        if video_file and youtube_url:
            raise serializers.ValidationError(
                'Provide only one of video_file or youtube_url, not both'
            )

        return attrs


class TaskMCQSerializer(serializers.ModelSerializer):
    """Serializer for MCQ details"""
    choice_1_text = serializers.CharField(required=True, max_length=500, error_messages={
        'required': 'Choice 1 text is required',
        'blank': 'Choice 1 text cannot be blank'
    })
    choice_2_text = serializers.CharField(required=True, max_length=500, error_messages={
        'required': 'Choice 2 text is required',
        'blank': 'Choice 2 text cannot be blank'
    })
    solution_explanation = serializers.CharField(required=True, error_messages={
        'required': 'Solution explanation is required',
        'blank': 'Solution explanation cannot be blank'
    })

    class Meta:
        model = TaskMCQ
        fields = [
            'id', 'question',
            'choice_1_text', 'choice_1_is_correct',
            'choice_2_text', 'choice_2_is_correct',
            'choice_3_text', 'choice_3_is_correct',
            'choice_4_text', 'choice_4_is_correct',
            'solution_explanation'
        ]
        read_only_fields = ['id', 'question']


class TaskTestCaseSerializer(serializers.ModelSerializer):
    """Serializer for test cases"""

    class Meta:
        model = TaskTestCase
        fields = [
            'id', 'input_data', 'expected_output',
            'is_sample', 'hidden', 'score_weight', 'order'
        ]
        read_only_fields = ['id']


class TaskCodingSerializer(serializers.ModelSerializer):
    """Serializer for coding question details"""
    test_cases = TaskTestCaseSerializer(many=True, read_only=True)

    class Meta:
        model = TaskCoding
        fields = [
            'id', 'question', 'problem_description',
            'input_description', 'sample_input',
            'output_description', 'sample_output',
            'language', 'constraints', 'hints', 'starter_code', 'test_cases'
        ]
        read_only_fields = ['id', 'question']


class TaskQuestionSerializer(serializers.ModelSerializer):
    """Serializer for task questions with nested details"""
    mcq_details = TaskMCQSerializer(read_only=True)
    coding_details = TaskCodingSerializer(read_only=True)
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = TaskQuestion
        fields = [
            'id', 'question_id', 'task', 'question_type', 'question_text',
            'marks', 'order', 'mcq_details', 'coding_details', 'is_completed',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'question_id', 'created_at', 'updated_at']

    def get_is_completed(self, obj):
        """Check if student has completed this question"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False

        student = request.user

        try:
            # Check if there's a completed submission for this question
            from student.models import ContentSubmission
            return ContentSubmission.objects.filter(
                student=student,
                question=obj,
                completed=True
            ).exists()
        except Exception as e:
            logger.error(f"Error checking question completion: {e}")
            return False


class TaskQuestionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating task questions"""
    mcq_data = TaskMCQSerializer(required=False)
    coding_data = TaskCodingSerializer(required=False)

    class Meta:
        model = TaskQuestion
        fields = [
            'task', 'question_type', 'question_text', 'marks', 'order',
            'mcq_data', 'coding_data'
        ]

    def validate(self, attrs):
        question_type = attrs.get('question_type')
        mcq_data = attrs.get('mcq_data')
        coding_data = attrs.get('coding_data')

        if question_type == 'mcq' and not mcq_data:
            raise serializers.ValidationError({
                'mcq_data': 'MCQ data is required for MCQ questions'
            })

        if question_type == 'coding' and not coding_data:
            raise serializers.ValidationError({
                'coding_data': 'Coding data is required for coding questions'
            })

        return attrs

    def create(self, validated_data):
        mcq_data = validated_data.pop('mcq_data', None)
        coding_data = validated_data.pop('coding_data', None)

        question = TaskQuestion.objects.create(**validated_data)

        if mcq_data:
            TaskMCQ.objects.create(question=question, **mcq_data)

        if coding_data:
            TaskCoding.objects.create(question=question, **coding_data)

        return question

    def update(self, instance, validated_data):
        mcq_data = validated_data.pop('mcq_data', None)
        coding_data = validated_data.pop('coding_data', None)

        # Update base question fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update MCQ details if provided
        if mcq_data:
            if hasattr(instance, 'mcq_details'):
                # Update existing MCQ details
                mcq_instance = instance.mcq_details
                for attr, value in mcq_data.items():
                    setattr(mcq_instance, attr, value)
                mcq_instance.save()
            else:
                # Create new MCQ details
                TaskMCQ.objects.create(question=instance, **mcq_data)

        # Update coding details if provided
        if coding_data:
            if hasattr(instance, 'coding_details'):
                # Update existing coding details
                coding_instance = instance.coding_details
                for attr, value in coding_data.items():
                    setattr(coding_instance, attr, value)
                coding_instance.save()
            else:
                # Create new coding details
                TaskCoding.objects.create(question=instance, **coding_data)

        return instance


class TaskTextBlockSerializer(serializers.ModelSerializer):
    """Serializer for text blocks"""

    class Meta:
        model = TaskTextBlock
        fields = ['id', 'page', 'content', 'order']
        read_only_fields = ['id']


class TaskCodeBlockSerializer(serializers.ModelSerializer):
    """Serializer for code blocks"""

    class Meta:
        model = TaskCodeBlock
        fields = ['id', 'page', 'language', 'code', 'title', 'order']
        read_only_fields = ['id']


class TaskVideoBlockSerializer(serializers.ModelSerializer):
    """Serializer for video blocks"""
    youtube_embed_id = serializers.SerializerMethodField()

    class Meta:
        model = TaskVideoBlock
        fields = ['id', 'page', 'title', 'youtube_url', 'youtube_embed_id', 'description', 'order']
        read_only_fields = ['id']
    def get_youtube_embed_id(self, obj):
        return obj.get_youtube_embed_id()


class TaskRichTextPageSerializer(serializers.ModelSerializer):
    """Serializer for rich text pages with nested blocks (pages don't require completion tracking)"""
    text_blocks = TaskTextBlockSerializer(many=True, read_only=True)
    code_blocks = TaskCodeBlockSerializer(many=True, read_only=True)
    video_blocks = TaskVideoBlockSerializer(many=True, read_only=True)

    class Meta:
        model = TaskRichTextPage
        fields = [
            'id', 'page_id', 'task', 'title', 'slug', 'order',
            'text_blocks', 'code_blocks', 'video_blocks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'page_id', 'slug', 'created_at', 'updated_at']


class TaskDetailSerializer(serializers.ModelSerializer):
    """Enhanced task serializer with all content"""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True, allow_null=True)
    is_active = serializers.SerializerMethodField()

    # Task content (use SerializerMethodField to pass context)
    documents = serializers.SerializerMethodField()
    videos = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    richtext_pages = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'task_id', 'course', 'course_title', 'topic', 'topic_title',
            'title', 'description', 'status', 'instructions',
            'start_date', 'due_date', 'max_score', 'passing_score',
            'allow_late_submission', 'is_mandatory', 'order',
            'created_by', 'created_by_name', 'is_active',
            'documents', 'videos', 'questions', 'richtext_pages',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'task_id', 'created_by', 'created_at', 'updated_at']

    @extend_schema_field(serializers.BooleanField())
    def get_is_active(self, obj):
        return obj.is_active

    # Pass task in context to children for is_completed
    def get_documents(self, obj):
        serializer = TaskDocumentSerializer(obj.documents.all(), many=True, context={**self.context, 'task': obj})
        return serializer.data

    def get_videos(self, obj):
        serializer = TaskVideoSerializer(obj.videos.all(), many=True, context={**self.context, 'task': obj})
        return serializer.data

    def get_questions(self, obj):
        serializer = TaskQuestionSerializer(obj.questions.all(), many=True, context=self.context)
        return serializer.data

    def get_richtext_pages(self, obj):
        serializer = TaskRichTextPageSerializer(obj.richtext_pages.all(), many=True, context={**self.context, 'task': obj})
        return serializer.data


class TaskSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for task submissions"""
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_email = serializers.CharField(source='student.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)
    graded_by_name = serializers.CharField(source='graded_by.get_full_name', read_only=True, allow_null=True)
    is_late = serializers.SerializerMethodField()
    is_passed = serializers.SerializerMethodField()

    class Meta:
        model = TaskSubmission
        fields = [
            'id', 'submission_id', 'task', 'task_title', 'student',
            'student_name', 'student_email', 'submission_text',
            'submission_file', 'submission_links', 'status', 'score',
            'feedback', 'graded_by', 'graded_by_name', 'is_late',
            'is_passed', 'submitted_at', 'graded_at', 'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'submission_id', 'student', 'submitted_at', 'graded_at',
            'created_at', 'updated_at', 'is_late', 'is_passed'
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_is_late(self, obj):
        return obj.is_late

    @extend_schema_field(serializers.BooleanField())
    def get_is_passed(self, obj):
        return obj.is_passed

    def validate(self, attrs):
        # Check if task allows submissions
        task = attrs.get('task') or (self.instance.task if self.instance else None)
        if task and task.status != 'active':
            raise serializers.ValidationError({
                'task': 'This task is not accepting submissions'
            })

        # Check deadline for new submissions
        if not self.instance:  # New submission
            if task and task.due_date and task.due_date < timezone.now() and not task.allow_late_submission:
                raise serializers.ValidationError({
                    'task': 'Submission deadline has passed'
                })

        return attrs


class TaskSubmissionGradeSerializer(serializers.ModelSerializer):
    """Serializer for grading task submissions"""
    class Meta:
        model = TaskSubmission
        fields = ['score', 'feedback', 'status']

    def validate_score(self, value):
        if value < 0:
            raise serializers.ValidationError('Score cannot be negative')
        if self.instance and value > self.instance.task.max_score:
            raise serializers.ValidationError(
                f'Score cannot exceed maximum score of {self.instance.task.max_score}'
            )
        return value

    def validate_status(self, value):
        if value not in ['graded', 'returned']:
            raise serializers.ValidationError(
                'Status must be either "graded" or "returned"'
            )
        return value