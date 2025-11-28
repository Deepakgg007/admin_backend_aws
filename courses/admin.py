from django.contrib import admin
from .models import (
    Course, Syllabus, SyllabusTopic, Topic, Task, Enrollment, TaskSubmission,
    TaskDocument, TaskVideo, TaskQuestion, TaskMCQ, TaskCoding, TaskTestCase,
    TaskRichTextPage, TaskTextBlock, TaskCodeBlock, TaskVideoBlock
)
# ContentSubmission moved to student app
# ContentProgress moved to student app


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['course_id', 'title', 'slug', 'difficulty_level', 'status', 'is_featured', 'college', 'created_by', 'current_enrollments', 'created_at']
    list_filter = ['status', 'difficulty_level', 'is_featured', 'college', 'created_at']
    search_fields = ['course_id', 'title', 'description', 'slug']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['uuid_id', 'course_id', 'slug', 'current_enrollments', 'created_by', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('course_id', 'title', 'slug', 'description')
        }),
        ('Course Details', {
            'fields': ('difficulty_level', 'duration_hours', 'status', 'is_featured')
        }),
        ('Media', {
            'fields': ('thumbnail', 'intro_video', 'video_intro_url')
        }),
        ('Tracking', {
            'fields': ('current_enrollments',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'college', 'uuid_id', 'published_at', 'created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        """Superusers see all courses, college admins see only their college's courses"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs  # Superusers see everything
        # College admins see only their college's courses
        if hasattr(request.user, 'college') and request.user.college:
            return qs.filter(college=request.user.college)
        return qs.none()


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'is_published', 'created_at']
    list_filter = ['is_published', 'created_at']
    search_fields = ['title', 'course__title']
    readonly_fields = ['syllabus_id', 'created_at', 'updated_at']
    ordering = ['course', 'order']

    def get_queryset(self, request):
        """Superusers see all syllabi, college admins see only their college's syllabi"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'college') and request.user.college:
            return qs.filter(course__college=request.user.college)
        return qs.none()


@admin.register(SyllabusTopic)
class SyllabusTopicAdmin(admin.ModelAdmin):
    list_display = ['syllabus', 'topic', 'order']
    list_filter = ['syllabus']
    search_fields = ['syllabus__title', 'topic__title']
    ordering = ['syllabus', 'order']


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'is_preview', 'is_published', 'created_at']
    list_filter = ['is_preview', 'is_published', 'created_at']
    search_fields = ['title', 'course__title']
    readonly_fields = ['topic_id', 'created_at', 'updated_at']
    ordering = ['course', 'title']

    def get_queryset(self, request):
        """Superusers see all topics, college admins see only their college's topics"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'college') and request.user.college:
            return qs.filter(course__college=request.user.college)
        return qs.none()


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'topic', 'status', 'due_date', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'course__title', 'topic__title']
    readonly_fields = ['task_id', 'created_at', 'updated_at']
    ordering = ['course', 'order']

    def get_queryset(self, request):
        """Superusers see all tasks, college admins see only their college's tasks"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'college') and request.user.college:
            return qs.filter(course__college=request.user.college)
        return qs.none()


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'status', 'progress_percentage', 'enrolled_at', 'completed_at']
    list_filter = ['status', 'enrolled_at']
    search_fields = ['student__email', 'course__title']
    readonly_fields = ['enrollment_id', 'enrolled_at']
    ordering = ['-enrolled_at']


@admin.register(TaskSubmission)
class TaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'task', 'status', 'score', 'submitted_at', 'graded_at', 'graded_by']
    list_filter = ['status', 'submitted_at', 'graded_at']
    search_fields = ['student__email', 'task__title']
    readonly_fields = ['submission_id', 'created_at', 'updated_at']
    ordering = ['-submitted_at']


# ============================================
# Task Content Admin
# ============================================

@admin.register(TaskDocument)
class TaskDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'task', 'order', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['title', 'task__title']
    readonly_fields = ['document_id', 'uploaded_at', 'updated_at']
    ordering = ['task', 'order']


@admin.register(TaskVideo)
class TaskVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'task', 'has_video_file', 'has_youtube_url', 'order', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['title', 'task__title', 'youtube_url']
    readonly_fields = ['video_id', 'uploaded_at', 'updated_at']
    ordering = ['task', 'order']

    def has_video_file(self, obj):
        return bool(obj.video_file)
    has_video_file.boolean = True
    has_video_file.short_description = 'Video File'

    def has_youtube_url(self, obj):
        return bool(obj.youtube_url)
    has_youtube_url.boolean = True
    has_youtube_url.short_description = 'YouTube'


@admin.register(TaskQuestion)
class TaskQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_text_short', 'task', 'question_type', 'marks', 'order', 'created_at']
    list_filter = ['question_type', 'created_at']
    search_fields = ['question_text', 'task__title']
    readonly_fields = ['question_id', 'created_at', 'updated_at']
    ordering = ['task', 'order']

    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'


class TaskMCQInline(admin.StackedInline):
    model = TaskMCQ
    extra = 0
    can_delete = False


class TaskCodingInline(admin.StackedInline):
    model = TaskCoding
    extra = 0
    can_delete = False


@admin.register(TaskMCQ)
class TaskMCQAdmin(admin.ModelAdmin):
    list_display = ['question', 'get_correct_choices', 'has_explanation']
    search_fields = ['question__question_text', 'solution_explanation']
    readonly_fields = []

    def get_correct_choices(self, obj):
        correct = []
        if obj.choice_1_is_correct: correct.append('1')
        if obj.choice_2_is_correct: correct.append('2')
        if obj.choice_3_is_correct: correct.append('3')
        if obj.choice_4_is_correct: correct.append('4')
        return ', '.join(correct) if correct else 'None'
    get_correct_choices.short_description = 'Correct Choices'

    def has_explanation(self, obj):
        return bool(obj.solution_explanation)
    has_explanation.boolean = True
    has_explanation.short_description = 'Has Explanation'


class TaskTestCaseInline(admin.TabularInline):
    model = TaskTestCase
    extra = 1
    fields = ['input_data', 'expected_output', 'is_sample', 'hidden', 'score_weight', 'order']
    ordering = ['-is_sample', 'order']


@admin.register(TaskCoding)
class TaskCodingAdmin(admin.ModelAdmin):
    list_display = ['question', 'language', 'test_case_count', 'has_constraints', 'has_hints']
    list_filter = ['language']
    search_fields = ['question__question_text', 'problem_description']
    inlines = [TaskTestCaseInline]

    def test_case_count(self, obj):
        return obj.test_cases.count()
    test_case_count.short_description = 'Test Cases'

    def has_constraints(self, obj):
        return bool(obj.constraints)
    has_constraints.boolean = True

    def has_hints(self, obj):
        return bool(obj.hints)
    has_hints.boolean = True


@admin.register(TaskTestCase)
class TaskTestCaseAdmin(admin.ModelAdmin):
    list_display = ['coding_question', 'test_type', 'score_weight', 'order', 'created_at']
    list_filter = ['is_sample', 'hidden', 'created_at']
    search_fields = ['coding_question__question__question_text', 'input_data', 'expected_output']
    ordering = ['coding_question', '-is_sample', 'order']

    def test_type(self, obj):
        if obj.is_sample:
            return 'Sample'
        return 'Hidden' if obj.hidden else 'Test'
    test_type.short_description = 'Type'


# Rich Text Page Admin
class TaskTextBlockInline(admin.TabularInline):
    model = TaskTextBlock
    extra = 1
    fields = ['content', 'order']
    ordering = ['order']


class TaskCodeBlockInline(admin.TabularInline):
    model = TaskCodeBlock
    extra = 1
    fields = ['title', 'language', 'code', 'order']
    ordering = ['order']


class TaskVideoBlockInline(admin.TabularInline):
    model = TaskVideoBlock
    extra = 1
    fields = ['title', 'youtube_url', 'description', 'order']
    ordering = ['order']


@admin.register(TaskRichTextPage)
class TaskRichTextPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'task', 'slug', 'order', 'block_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['title', 'task__title', 'slug']
    readonly_fields = ['page_id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('title',)}
    ordering = ['task', 'order']
    inlines = [TaskTextBlockInline, TaskCodeBlockInline, TaskVideoBlockInline]

    def block_count(self, obj):
        text = obj.text_blocks.count()
        code = obj.code_blocks.count()
        video = obj.video_blocks.count()
        return f"{text + code + video} blocks"
    block_count.short_description = 'Content Blocks'


@admin.register(TaskTextBlock)
class TaskTextBlockAdmin(admin.ModelAdmin):
    list_display = ['page', 'content_preview', 'order']
    search_fields = ['page__title', 'content']
    ordering = ['page', 'order']

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(TaskCodeBlock)
class TaskCodeBlockAdmin(admin.ModelAdmin):
    list_display = ['title', 'page', 'language', 'order']
    list_filter = ['language']
    search_fields = ['page__title', 'title', 'code']
    ordering = ['page', 'order']


@admin.register(TaskVideoBlock)
class TaskVideoBlockAdmin(admin.ModelAdmin):
    list_display = ['title', 'page', 'youtube_url', 'order']
    search_fields = ['page__title', 'title', 'youtube_url']
    ordering = ['page', 'order']


# ContentSubmission admin moved to student app (student.admin.ContentSubmissionAdmin)
# ContentProgress admin moved to student app (student.admin.ContentProgressAdmin)
