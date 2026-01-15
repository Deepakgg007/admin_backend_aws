from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from coding.models import Challenge, PROGRAMMING_LANGUAGE_CHOICES
import uuid

# Import profile models
from .user_profile_models import (
    UserProfile, Badge, UserBadge,
    LeaderboardCache, UserActivity
)

User = get_user_model()

# Common status choices for all submissions
STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('ACCEPTED', 'Accepted'),
    ('WRONG_ANSWER', 'Wrong Answer'),
    ('RUNTIME_ERROR', 'Runtime Error'),
    ('TIME_LIMIT_EXCEEDED', 'Time Limit Exceeded'),
    ('COMPILATION_ERROR', 'Compilation Error'),
    ('MEMORY_LIMIT_EXCEEDED', 'Memory Limit Exceeded'),
    ('SYSTEM_ERROR', 'System Error'),
    ('PARTIAL', 'Partial'),
]

class CodingChallengeSubmission(models.Model):
    """
    Student submission for standalone coding challenges
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coding_submissions')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='coding_submissions')
    submitted_code = models.TextField()
    language = models.CharField(max_length=50, choices=PROGRAMMING_LANGUAGE_CHOICES, default='python')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING')
    passed_tests = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    runtime = models.FloatField(default=0.0, help_text='Runtime in milliseconds')
    memory_used = models.FloatField(default=0.0, help_text='Memory used in KB')
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Enhanced tracking fields
    test_results = models.JSONField(default=dict, blank=True, help_text='Detailed test case results')
    compilation_message = models.TextField(blank=True)
    is_best_submission = models.BooleanField(default=False, help_text='User\'s best submission for this challenge')

    class Meta:
        db_table = 'student_coding_challenge_submission'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['user', 'challenge']),
            models.Index(fields=['challenge', 'status']),
            models.Index(fields=['submitted_at']),
        ]
        verbose_name = "Coding Challenge Submission"
        verbose_name_plural = "Coding Challenge Submissions"

    def __str__(self):
        return f"{self.user.username} - {self.challenge.title} ({self.status})"

    def save(self, *args, **kwargs):
        # Mark as best submission if this is accepted
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.status == 'ACCEPTED':
            # Reset all other submissions for this user-challenge pair
            CodingChallengeSubmission.objects.filter(
                user=self.user, challenge=self.challenge
            ).exclude(pk=self.pk).update(is_best_submission=False)
            self.is_best_submission = True
            super().save(update_fields=['is_best_submission'])


class CompanyChallengeSubmission(models.Model):
    """
    Student submission for company-specific challenges
    References the external challenge ID from company_challenges system
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company_challenge_submissions')

    # Store company and concept info
    company_id = models.IntegerField(help_text='Company ID from company_challenges system')
    company_name = models.CharField(max_length=255, blank=True)
    concept_id = models.IntegerField(help_text='Concept ID from company_challenges system')
    concept_name = models.CharField(max_length=255, blank=True)

    # Challenge reference (external system)
    challenge_id = models.IntegerField(help_text='Challenge ID from coding_challenges system')
    challenge_slug = models.SlugField(help_text='Challenge slug for reference')
    challenge_title = models.CharField(max_length=255, blank=True)

    # Submission details
    submitted_code = models.TextField()
    language = models.CharField(max_length=50, choices=PROGRAMMING_LANGUAGE_CHOICES, default='python')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING')
    passed_tests = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    runtime = models.FloatField(default=0.0, help_text='Runtime in milliseconds')
    memory_used = models.FloatField(default=0.0, help_text='Memory used in KB')
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Enhanced tracking fields
    test_results = models.JSONField(default=dict, blank=True, help_text='Detailed test case results')
    compilation_message = models.TextField(blank=True)
    is_best_submission = models.BooleanField(default=False, help_text='User\'s best submission for this challenge in this company')

    class Meta:
        db_table = 'student_company_challenge_submission'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['user', 'company_id', 'challenge_id']),
            models.Index(fields=['challenge_id', 'status']),
            models.Index(fields=['submitted_at']),
        ]
        verbose_name = "Company Challenge Submission"
        verbose_name_plural = "Company Challenge Submissions"

    def __str__(self):
        return f"{self.user.username} - {self.company_name} - {self.challenge_title} ({self.status})"

    def save(self, *args, **kwargs):
        # Mark as best submission if this is accepted
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.status == 'ACCEPTED':
            # Reset all other submissions for this user-challenge-company pair
            CompanyChallengeSubmission.objects.filter(
                user=self.user,
                company_id=self.company_id,
                challenge_id=self.challenge_id
            ).exclude(pk=self.pk).update(is_best_submission=False)
            self.is_best_submission = True
            super().save(update_fields=['is_best_submission'])


# Legacy model alias for backward compatibility
class StudentChallengeSubmission(CodingChallengeSubmission):
    """
    Legacy alias for backward compatibility
    """
    class Meta:
        proxy = True
        verbose_name = "Student Challenge Submission (Legacy)"
        verbose_name_plural = "Student Challenge Submissions (Legacy)"


class ContentSubmission(models.Model):
    """
    Track individual content item completions and submissions
    For videos, documents, pages, and questions
    """
    SUBMISSION_TYPE_CHOICES = [
        ('question', 'Question Submission'),
        ('document', 'Document Completion'),
        ('video', 'Video Completion'),
        ('page', 'Page Completion'),
    ]

    submission_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='content_submissions')
    task = models.ForeignKey('courses.Task', on_delete=models.CASCADE, related_name='content_submissions')

    # Content type and reference
    submission_type = models.CharField(max_length=20, choices=SUBMISSION_TYPE_CHOICES)

    # Foreign keys to specific content (nullable, only one should be set)
    question = models.ForeignKey('courses.TaskQuestion', on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    document = models.ForeignKey('courses.TaskDocument', on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    video = models.ForeignKey('courses.TaskVideo', on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    page = models.ForeignKey('courses.TaskRichTextPage', on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    mcq_set_question = models.ForeignKey('courses.TaskMCQSetQuestion', on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')

    # Question-specific fields
    mcq_selected_choice = models.IntegerField(null=True, blank=True, help_text="Selected choice number (1-4) for MCQ")
    code_submitted = models.TextField(blank=True, null=True, help_text="Submitted code for coding questions")
    answer_text = models.TextField(blank=True, null=True, help_text="Text answer or notes")

    # Grading and completion
    is_correct = models.BooleanField(null=True, blank=True, help_text="For MCQ: indicates correctness")
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Points earned")
    completed = models.BooleanField(default=False, help_text="Marks content as completed")

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'content_submissions'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['student', 'task']),
            models.Index(fields=['submission_type']),
        ]
        # Ensure one submission per student per content item
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'question'],
                condition=models.Q(question__isnull=False),
                name='unique_student_question'
            ),
            models.UniqueConstraint(
                fields=['student', 'document'],
                condition=models.Q(document__isnull=False),
                name='unique_student_document'
            ),
            models.UniqueConstraint(
                fields=['student', 'video'],
                condition=models.Q(video__isnull=False),
                name='unique_student_video'
            ),
            models.UniqueConstraint(
                fields=['student', 'page'],
                condition=models.Q(page__isnull=False),
                name='unique_student_page'
            ),
            models.UniqueConstraint(
                fields=['student', 'mcq_set_question'],
                condition=models.Q(mcq_set_question__isnull=False),
                name='unique_student_mcq_set_question'
            ),
        ]
        verbose_name = "Content Submission"
        verbose_name_plural = "Content Submissions"

    def __str__(self):
        content_ref = ""
        if self.question:
            content_ref = f"Question: {self.question.question_text[:30]}..."
        elif self.document:
            content_ref = f"Document: {self.document.title or 'Untitled'}"
        elif self.video:
            content_ref = f"Video: {self.video.title or 'Untitled'}"
        elif self.page:
            content_ref = f"Page: {self.page.title or 'Untitled'}"
        elif self.mcq_set_question:
            content_ref = f"MCQ Set Question: {self.mcq_set_question.question_text[:30]}..."
        return f"{self.student.email} - {content_ref} ({self.submission_type})"


class ContentProgress(models.Model):
    """
    Track completion of individual content items (videos, documents, questions)
    EXCLUDES pages from progress calculation
    """

    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('document', 'Document'),
        ('question', 'Question'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_progress')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='student_content_progress')
    task = models.ForeignKey('courses.Task', on_delete=models.CASCADE, related_name='student_content_progress')

    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id = models.IntegerField(help_text="ID of the video/document/question")

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'student_content_progress'
        unique_together = ['user', 'content_type', 'content_id']
        indexes = [
            models.Index(fields=['user', 'course']),
            models.Index(fields=['user', 'task']),
            models.Index(fields=['is_completed']),
        ]
        verbose_name = "Content Progress"
        verbose_name_plural = "Content Progress"

    def __str__(self):
        return f"{self.user.username} - {self.content_type} {self.content_id}"

    @classmethod
    def mark_completed(cls, user, course, task, content_type, content_id):
        """Mark a content item as completed"""
        from django.utils import timezone

        progress, created = cls.objects.get_or_create(
            user=user,
            course=course,
            task=task,
            content_type=content_type,
            content_id=content_id,
            defaults={'is_completed': True, 'completed_at': timezone.now()}
        )

        if not created and not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = timezone.now()
            progress.save(update_fields=['is_completed', 'completed_at'])

        return progress

    @classmethod
    def get_course_progress(cls, user, course):
        """
        Calculate course progress based on completed content items
        ONLY counts videos, documents, coding questions, and MCQ Set questions - NO PAGES or OLD MCQs
        Returns: (completed_count, total_count, percentage)
        """
        from courses.models import Task, TaskVideo, TaskDocument, TaskQuestion, TaskMCQSet, TaskMCQSetQuestion, Course, Topic

        # Ensure course is a Course instance
        if not isinstance(course, Course):
            try:
                if isinstance(course, int):
                    course = Course.objects.get(id=course)
                elif isinstance(course, str):
                    try:
                        course_id = int(course)
                        course = Course.objects.get(id=course_id)
                    except (ValueError, Course.DoesNotExist):
                        course = Course.objects.get(title=course)
                else:
                    return 0, 0, 0.0
            except Course.DoesNotExist:
                return 0, 0, 0.0

        # Get tasks BOTH from topics AND directly from course
        # Tasks can be attached either way
        from django.db.models import Q

        # Get topics directly by course
        topics = Topic.objects.filter(course=course).distinct()

        # Get tasks - either through topics OR directly attached to course
        tasks = Task.objects.filter(
            Q(topic__in=topics) | Q(course=course)
        ).distinct()

        if not tasks.exists():
            return 0, 0, 0.0

        # Count total content items (excluding pages and old MCQ questions)
        total_videos = TaskVideo.objects.filter(task__in=tasks).count()
        total_documents = TaskDocument.objects.filter(task__in=tasks).count()

        # Only count coding questions (old MCQ questions are deprecated)
        total_coding_questions = TaskQuestion.objects.filter(task__in=tasks, question_type='coding').count()

        # Count MCQ Set questions (new system for MCQs)
        mcq_sets = TaskMCQSet.objects.filter(task__in=tasks)
        total_mcq_set_questions = TaskMCQSetQuestion.objects.filter(mcq_set__in=mcq_sets).count()

        total_count = total_videos + total_documents + total_coding_questions + total_mcq_set_questions

        if total_count == 0:
            return 0, 0, 0.0

        # Count completed items for this course
        completed_count = cls.objects.filter(
            user=user,
            course=course,
            is_completed=True
        ).count()

        percentage = (completed_count / total_count) * 100

        return completed_count, total_count, round(percentage, 2)
