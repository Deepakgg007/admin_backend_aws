import json
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
import uuid

User = get_user_model()


class Course(models.Model):
    """Main course model"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    # Identifiers
    uuid_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    course_id = models.CharField(max_length=20, unique=True, verbose_name="Course ID", blank=True, null=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField()

    # Course details
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    duration_hours = models.IntegerField(help_text="Estimated course duration in hours", default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Media
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)
    intro_video = models.FileField(upload_to='course_intro_videos/', blank=True, null=True, verbose_name="Introduction Video")
    video_intro_url = models.URLField(blank=True, null=True, help_text="Introduction video URL (YouTube, Vimeo, etc.)")

    # Tracking
    current_enrollments = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_courses')
    college = models.ForeignKey('api.College', on_delete=models.CASCADE, null=True, blank=True, related_name='courses', help_text="College that owns this course")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'courses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status', 'is_featured']),
            models.Index(fields=['college']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            # Ensure unique slug
            counter = 1
            original_slug = self.slug
            while Course.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)


class Syllabus(models.Model):
    """Course syllabus/curriculum structure"""
    syllabus_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='syllabi')

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    order = models.IntegerField(default=0, help_text="Display order within course")

    # Many-to-many relationship with Topic through SyllabusTopic
    topics = models.ManyToManyField('Topic', through='SyllabusTopic', blank=True, related_name='syllabi')

    # Access control
    is_published = models.BooleanField(default=True)
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'syllabi'
        ordering = ['order', 'created_at']
        unique_together = ['course', 'order']
        verbose_name_plural = 'Syllabi'

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    def get_ordered_topics(self):
        """Returns topics ordered by their position in the syllabus"""
        return self.topics.through.objects.filter(syllabus=self).order_by('order').select_related('topic')


class SyllabusTopic(models.Model):
    """Through model for ordered relationship between Syllabus and Topic"""
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE)
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0, help_text="Order of topic in syllabus")

    class Meta:
        db_table = 'syllabus_topics'
        ordering = ['order']
        unique_together = ('syllabus', 'topic')

    def __str__(self):
        return f"{self.syllabus.title} - {self.topic.title} (Order: {self.order})"


class Topic(models.Model):
    topic_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='topics', verbose_name="Associated Course", null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    # Access control
    is_preview = models.BooleanField(default=False, help_text="Available before enrollment")
    is_published = models.BooleanField(default=True)
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'topics'
        ordering = ['title', 'created_at']

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class Task(models.Model):
    """Tasks/assignments associated with topics or courses"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    ]

    task_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='tasks')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')

    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Instructions and resources
    instructions = models.TextField(blank=True, null=True)
    resource_file = models.FileField(upload_to='task_resources/', blank=True, null=True)
    reference_links = models.JSONField(default=list, blank=True, help_text="Array of reference URLs")

    # Deadlines and timing
    start_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)

    # Grading
    passing_score = models.IntegerField(default=60)

    # Settings
    allow_late_submission = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    # Timestamps
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tasks'
        ordering = ['order', 'due_date', 'created_at']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def is_active(self):
        from django.utils import timezone
        if self.status != 'active':
            return False
        if self.start_date and self.start_date > timezone.now():
            return False
        return True


class TaskDocument(models.Model):
    """Documents attached to tasks"""
    document_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='documents')

    title = models.CharField(max_length=255, blank=True, null=True)
    document = models.FileField(upload_to='task_documents/', verbose_name="Document File")
    description = models.TextField(blank=True, null=True)

    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within task")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_documents'
        ordering = ['order', 'uploaded_at']
        indexes = [
            models.Index(fields=['task', 'order']),
        ]

    def __str__(self):
        return f"Document: {self.title or self.document.name} - {self.task.title}"


import re
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


def validate_youtube_url(value):
    """Validate YouTube URL format"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    if not re.match(youtube_regex, value):
        raise ValidationError('Enter a valid YouTube URL.')
    return value


class TaskVideo(models.Model):
    """Videos attached to tasks (uploaded or YouTube)"""
    video_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='videos')

    title = models.CharField(max_length=255, blank=True, null=True)
    video_file = models.FileField(
        upload_to='task_videos/',
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'mkv', 'webm'])],
        verbose_name="Video File",
        blank=True,
        null=True
    )
    youtube_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        validators=[validate_youtube_url],
        verbose_name="YouTube URL"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Video Description")

    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within task")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_videos'
        ordering = ['order', 'uploaded_at']
        indexes = [
            models.Index(fields=['task', 'order']),
        ]

    def __str__(self):
        if self.youtube_url:
            return f"YouTube Video: {self.title or self.youtube_url} - {self.task.title}"
        return f"Video: {self.title or self.video_file.name} - {self.task.title}"

    def clean(self):
        """Validate that either video file or YouTube URL is provided, but not both"""
        if not self.video_file and not self.youtube_url:
            raise ValidationError('Either a video file or a YouTube URL is required.')
        if self.video_file and self.youtube_url:
            raise ValidationError('Please provide only one of video file or YouTube URL, not both.')
        return super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_youtube_embed_id(self):
        """Extract YouTube video ID from URL for embedding"""
        if self.youtube_url:
            youtube_regex = re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)')
            match = youtube_regex.search(self.youtube_url)
            if match:
                return match.group(1)
        return None


class TaskQuestion(models.Model):
    """Questions attached to tasks (MCQ or Coding)"""
    QUESTION_TYPE_CHOICES = [
        ('mcq', 'Multiple Choice Question'),
        ('coding', 'Coding Question'),
    ]

    question_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='questions')

    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES, default='mcq')
    question_text = models.TextField(verbose_name="Question Text")
    marks = models.PositiveIntegerField(default=1, help_text="Marks for this question")

    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_questions'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['task', 'order']),
            models.Index(fields=['question_type']),
        ]

    def __str__(self):
        return f"[{self.get_question_type_display()}] {self.question_text[:50]}... - {self.task.title}"


class TaskMCQ(models.Model):
    """MCQ question details"""
    question = models.OneToOneField(TaskQuestion, on_delete=models.CASCADE, related_name='mcq_details')

    # Choice 1 (Required)
    choice_1_text = models.CharField(max_length=500, verbose_name="Choice 1")
    choice_1_is_correct = models.BooleanField(default=False, verbose_name="Choice 1 Correct")

    # Choice 2 (Required)
    choice_2_text = models.CharField(max_length=500, verbose_name="Choice 2")
    choice_2_is_correct = models.BooleanField(default=False, verbose_name="Choice 2 Correct")

    # Choice 3 (Optional)
    choice_3_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Choice 3")
    choice_3_is_correct = models.BooleanField(default=False, verbose_name="Choice 3 Correct")

    # Choice 4 (Optional)
    choice_4_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Choice 4")
    choice_4_is_correct = models.BooleanField(default=False, verbose_name="Choice 4 Correct")

    # Solution explanation (Required)
    solution_explanation = models.TextField(
        verbose_name="Solution Explanation",
        help_text="Explanation for the correct answer"
    )

    class Meta:
        db_table = 'task_mcq_details'
        verbose_name = "MCQ Details"
        verbose_name_plural = "MCQ Details"

    def __str__(self):
        return f"MCQ Details for: {self.question.question_text[:50]}..."

    def clean(self):
        """Validate MCQ has at least 2 choices and at least 1 correct answer"""
        choices = [self.choice_1_text, self.choice_2_text, self.choice_3_text, self.choice_4_text]
        if sum(1 for choice in choices if choice) < 2:
            raise ValidationError("MCQ questions must have at least two choices.")

        correct_answers = [
            self.choice_1_is_correct,
            self.choice_2_is_correct,
            self.choice_3_is_correct,
            self.choice_4_is_correct
        ]
        if not any(correct_answers):
            raise ValidationError("MCQ questions must have at least one correct choice.")

        if not self.solution_explanation:
            raise ValidationError("MCQ questions must have a solution explanation.")


class TaskCoding(models.Model):
    """Coding question details"""
    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('java', 'Java'),
        ('cpp', 'C++'),
        ('c', 'C'),
        ('javascript', 'JavaScript'),
        ('csharp', 'C#'),
        ('ruby', 'Ruby'),
        ('go', 'Go'),
        ('rust', 'Rust'),
        ('php', 'PHP'),
        ('typescript', 'TypeScript'),
        ('kotlin', 'Kotlin'),
        ('swift', 'Swift'),
    ]

    question = models.OneToOneField(TaskQuestion, on_delete=models.CASCADE, related_name='coding_details')

    # Problem description
    problem_description = models.TextField(
        verbose_name="Problem Description",
        help_text="Full description of the coding problem"
    )

    # Input specifications
    input_description = models.TextField(
        verbose_name="Input Description",
        help_text="Describes the format of input data"
    )
    sample_input = models.TextField(
        verbose_name="Sample Input",
        help_text="Example input for testing (e.g., '5 3')"
    )

    # Output specifications
    output_description = models.TextField(
        verbose_name="Output Format Description",
        help_text="Describes the format/structure of expected output"
    )
    sample_output = models.TextField(
        verbose_name="Sample Output",
        help_text="Expected output for the sample input"
    )

    # Programming language
    language = models.CharField(
        max_length=20,
        choices=LANGUAGE_CHOICES,
        default='python',
        help_text="Required programming language"
    )

    # Constraints and hints
    constraints = models.TextField(
        blank=True,
        null=True,
        help_text="Problem constraints (time/space complexity, input limits)"
    )
    hints = models.TextField(
        blank=True,
        null=True,
        help_text="Hints to help solve the problem"
    )
    
    # Starter code
    starter_code = models.TextField(
        blank=True,
        null=True,
        help_text="Pre-written starter code for students to begin with"
    )

    class Meta:
        db_table = 'task_coding_details'
        verbose_name = "Coding Question Details"
        verbose_name_plural = "Coding Question Details"

    def __str__(self):
        return f"Coding Details ({self.language}) for: {self.question.question_text[:50]}..."


class TaskTestCase(models.Model):
    """Test cases for coding questions"""
    coding_question = models.ForeignKey(
        TaskCoding,
        on_delete=models.CASCADE,
        related_name='test_cases'
    )

    input_data = models.TextField(
        verbose_name="Input Data",
        help_text="Input data for this test case"
    )
    expected_output = models.TextField(
        verbose_name="Expected Output",
        help_text="Expected output for this input"
    )

    is_sample = models.BooleanField(
        default=False,
        help_text="If true, this test case is visible to students"
    )
    hidden = models.BooleanField(
        default=False,
        help_text="If true, this test case is hidden during grading"
    )
    score_weight = models.PositiveIntegerField(
        default=1,
        help_text="Weight/points for this test case"
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_test_cases'
        ordering = ['-is_sample', 'order', 'created_at']
        indexes = [
            models.Index(fields=['coding_question', 'is_sample']),
        ]

    def __str__(self):
        test_type = "Sample" if self.is_sample else ("Hidden" if self.hidden else "Test")
        return f"{test_type} Case for {self.coding_question.question.question_text[:30]}..."


class TaskMCQSet(models.Model):
    """MCQ Set/Assessment - A collection of related MCQ questions"""
    mcq_set_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='mcq_sets')

    title = models.CharField(max_length=255, verbose_name="MCQ Set Title", help_text="e.g., 'Java Basics - Test 1'")
    description = models.TextField(blank=True, null=True, verbose_name="Description", help_text="Optional description for this MCQ set")

    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_mcq_sets'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['task', 'order']),
        ]

    def __str__(self):
        return f"{self.title} - {self.task.title}"

    @property
    def total_marks(self):
        """Calculate total marks for all questions in this set"""
        return sum(q.marks for q in self.mcq_questions.all())

    @property
    def question_count(self):
        """Get total number of questions in this set"""
        return self.mcq_questions.count()


class TaskMCQSetQuestion(models.Model):
    """Individual MCQ question within an MCQ Set"""
    mcq_set = models.ForeignKey(TaskMCQSet, on_delete=models.CASCADE, related_name='mcq_questions')

    question_text = models.TextField(verbose_name="Question Text")
    marks = models.PositiveIntegerField(default=1, help_text="Marks for this question")

    # Choice 1 (Required)
    choice_1_text = models.CharField(max_length=500, verbose_name="Choice 1")
    choice_1_is_correct = models.BooleanField(default=False, verbose_name="Choice 1 Correct")

    # Choice 2 (Required)
    choice_2_text = models.CharField(max_length=500, verbose_name="Choice 2")
    choice_2_is_correct = models.BooleanField(default=False, verbose_name="Choice 2 Correct")

    # Choice 3 (Optional)
    choice_3_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Choice 3")
    choice_3_is_correct = models.BooleanField(default=False, verbose_name="Choice 3 Correct")

    # Choice 4 (Optional)
    choice_4_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Choice 4")
    choice_4_is_correct = models.BooleanField(default=False, verbose_name="Choice 4 Correct")

    # Solution explanation (Required)
    solution_explanation = models.TextField(
        verbose_name="Solution Explanation",
        help_text="Explanation for the correct answer"
    )

    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within MCQ set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_mcq_set_questions'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['mcq_set', 'order']),
        ]

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:50]}... - {self.mcq_set.title}"

    def clean(self):
        """Validate MCQ has at least 2 choices and at least 1 correct answer"""
        choices = [self.choice_1_text, self.choice_2_text, self.choice_3_text, self.choice_4_text]
        if sum(1 for choice in choices if choice) < 2:
            raise ValidationError("MCQ questions must have at least two choices.")

        correct_answers = [
            self.choice_1_is_correct,
            self.choice_2_is_correct,
            self.choice_3_is_correct,
            self.choice_4_is_correct
        ]
        if not any(correct_answers):
            raise ValidationError("MCQ questions must have at least one correct choice.")

        if not self.solution_explanation:
            raise ValidationError("Solution explanation is required.")


class TaskRichTextPage(models.Model):
    """Rich text content pages with mixed content blocks"""
    page_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='richtext_pages')
    title = models.CharField(max_length=255, verbose_name="Page Title")
    slug = models.SlugField(max_length=255, help_text="URL-friendly title")
    order = models.PositiveIntegerField(default=0, verbose_name="Order", help_text="Display order within task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_richtext_pages'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['task', 'order']),
            models.Index(fields=['slug']),
        ]
        unique_together = ['task', 'slug']

    def __str__(self):
        return f"{self.title} - {self.task.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class TaskTextBlock(models.Model):
    """Text content blocks within rich text pages"""
    page = models.ForeignKey(TaskRichTextPage, on_delete=models.CASCADE, related_name='text_blocks')

    content = models.TextField(verbose_name="Text Content")
    order = models.PositiveIntegerField(default=0, verbose_name="Order")

    class Meta:
        db_table = 'task_text_blocks'
        ordering = ['order']
        indexes = [
            models.Index(fields=['page', 'order']),
        ]

    def __str__(self):
        return f"Text Block {self.order} - {self.page.title}"


class TaskCodeBlock(models.Model):
    """Code snippet blocks within rich text pages"""
    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('java', 'Java'),
        ('javascript', 'JavaScript'),
        ('cpp', 'C++'),
        ('c', 'C'),
        ('html', 'HTML'),
        ('css', 'CSS'),
        ('sql', 'SQL'),
        ('bash', 'Bash'),
        ('json', 'JSON'),
    ]

    page = models.ForeignKey(TaskRichTextPage, on_delete=models.CASCADE, related_name='code_blocks')

    language = models.CharField(max_length=50, choices=LANGUAGE_CHOICES, default='python')
    code = models.TextField(verbose_name="Code Content")
    title = models.CharField(max_length=255, blank=True, null=True, help_text="Optional code block title")

    order = models.PositiveIntegerField(default=0, verbose_name="Order")

    class Meta:
        db_table = 'task_code_blocks'
        ordering = ['order']
        indexes = [
            models.Index(fields=['page', 'order']),
        ]

    def __str__(self):
        return f"Code Block ({self.language}) {self.order} - {self.page.title}"


class TaskVideoBlock(models.Model):
    """Video embed blocks within rich text pages"""
    page = models.ForeignKey(TaskRichTextPage, on_delete=models.CASCADE, related_name='video_blocks')

    title = models.CharField(max_length=255, verbose_name="Video Title", blank=True, null=True)
    youtube_url = models.URLField(
        max_length=500,
        verbose_name="YouTube URL",
        help_text="YouTube video URL"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Video Description")

    order = models.PositiveIntegerField(default=0, verbose_name="Order")

    class Meta:
        db_table = 'task_video_blocks'
        ordering = ['order']
        indexes = [
            models.Index(fields=['page', 'order']),
        ]

    def __str__(self):
        return f"Video Block {self.order}: {self.title or 'Untitled'} - {self.page.title}"

    def get_youtube_embed_id(self):
        """Extract YouTube video ID from URL for embedding"""
        if self.youtube_url:
            youtube_regex = re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)')
            match = youtube_regex.search(self.youtube_url)
            if match:
                return match.group(1)
        return None


class TaskHighlightBlock(models.Model):
    """Highlight content blocks - displays content exactly as entered with dark background"""
    page = models.ForeignKey(TaskRichTextPage, on_delete=models.CASCADE, related_name='highlight_blocks')

    content = models.TextField(
        verbose_name="Highlight Content",
        help_text="Content will be displayed exactly as entered with preserved formatting"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Order")

    class Meta:
        db_table = 'task_highlight_blocks'
        ordering = ['order']
        indexes = [
            models.Index(fields=['page', 'order']),
        ]

    def __str__(self):
        return f"Highlight Block {self.order} - {self.page.title}"


class Enrollment(models.Model):
    """Track student enrollments in courses"""
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
    ]

    enrollment_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    # Timestamps
    enrolled_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'enrollments'
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.email} - {self.course.title}"

    def calculate_progress(self):
        """Calculate progress based on individually completed content items (videos, documents, questions ONLY - NO PAGES)"""
        from student.models import ContentProgress

        # Use ContentProgress model to get accurate completion data
        completed_count, total_count, percentage = ContentProgress.get_course_progress(
            user=self.student,
            course=self.course
        )

        self.progress_percentage = percentage

        # Update status based on progress
        was_completed_before = self.status == 'completed'

        # Update last_accessed timestamp
        self.last_accessed = timezone.now()

        if percentage >= 100:
            self.status = 'completed'
            if not self.completed_at:
                self.completed_at = timezone.now()

                # Update UserProfile courses_completed counter
                if not was_completed_before:
                    from student.user_profile_models import UserProfile
                    profile, created = UserProfile.objects.get_or_create(user=self.student)
                    profile.courses_completed += 1
                    profile.save(update_fields=['courses_completed'])
        elif percentage > 0:
            self.status = 'in_progress'
            if not self.started_at:
                self.started_at = timezone.now()

        self.save(update_fields=['progress_percentage', 'status', 'completed_at', 'started_at', 'last_accessed'])
        return self.progress_percentage


class TaskSubmission(models.Model):
    """Student task submissions"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned for Revision'),
        ('completed', 'Completed'),  # New: For passive content views (pages, videos, etc.)
    ]

    submission_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='submissions')  # Assuming Task model name
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_submissions')

    # Submission content
    submission_text = models.TextField(blank=True, null=True)
    submission_file = models.FileField(upload_to='task_submissions/', blank=True, null=True)
    submission_links = models.JSONField(default=list, blank=True)

    # Content completion tracking (for videos, documents, questions)
    completed_content = models.JSONField(default=dict, blank=True, help_text="Tracks completed content items: {content_type: [content_ids]}")

    # Grading
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_submissions')

    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_submissions'
        unique_together = ['task', 'student']
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student.email} - {self.task.title}"

    @property
    def is_late(self):
        if self.submitted_at and self.task.due_date:
            return self.submitted_at > self.task.due_date
        return False

    @property
    def is_passed(self):
        if self.score is not None:
            return self.score >= self.task.passing_score
        return False

    # New: Check if this is a completion marker (not a real submission)
    def is_completion_marker(self):
        if self.status != 'completed' or not self.submission_text:
            return False
        try:
            data = json.loads(self.submission_text)
            return data.get('completion') == True
        except (json.JSONDecodeError, AttributeError):
            return False

    # New: Extract content_type and content_id from marker
    def get_completion_info(self):
        if self.is_completion_marker():
            try:
                data = json.loads(self.submission_text)
                return {
                    'content_type': data.get('content_type'),
                    'content_id': data.get('content_id')
                }
            except (json.JSONDecodeError, AttributeError):
                return {}
        return {}

    # Optional: Override save to set submitted_at for completions
    def save(self, *args, **kwargs):
        if self.status == 'completed' and not self.submitted_at:
            self.submitted_at = timezone.now()
        super().save(*args, **kwargs)

# ContentSubmission model moved to student app (student.models.ContentSubmission)
# Only handles video, document, and question submissions (NO page submissions)
