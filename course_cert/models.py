from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from courses.models import Course, Enrollment


class Certification(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="certifications"
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    passing_score = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Percentage score required to pass (1-100)"
    )
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Time limit for completing the certification in minutes"
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text="Maximum number of attempts allowed per user"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active certifications are visible to students"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Certification"
        verbose_name_plural = "Certifications"
        indexes = [
            models.Index(fields=['course', 'is_active']),
        ]

    def clean(self):
        if self.passing_score > 100 or self.passing_score < 1:
            raise ValidationError("Passing score must be between 1 and 100")
        if self.duration_minutes < 1:
            raise ValidationError("Duration must be at least 1 minute")
        if self.max_attempts < 1:
            raise ValidationError("At least 1 attempt must be allowed")

    def __str__(self):
        return f"{self.title} - {self.course.title}"

    def get_total_weight(self):
        """Calculate total weight of all active questions"""
        return self.questions.filter(is_active=True).aggregate(
            total=models.Sum('weight')
        )['total'] or 0

    def get_pass_rate(self):
        """Calculate pass rate percentage"""
        completed = self.attempts.filter(completed_at__isnull=False)
        total = completed.count()
        if total == 0:
            return 0
        passed = completed.filter(passed=True).count()
        return round((passed / total) * 100, 2)

    def get_average_score(self):
        """Calculate average score of all completed attempts"""
        result = self.attempts.filter(
            completed_at__isnull=False
        ).aggregate(avg=models.Avg('score'))
        return round(result['avg'] or 0, 2)


class CertificationQuestion(models.Model):
    certification = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="questions"
    )
    text = models.TextField(help_text="The question text")
    is_multiple_correct = models.BooleanField(
        default=False,
        help_text="True if multiple options can be correct"
    )
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Weight/points for this question"
    )
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order in the certification"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive questions are not shown to students"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Certification Question"
        verbose_name_plural = "Certification Questions"
        constraints = [
            models.UniqueConstraint(
                fields=["certification", "order"],
                name="unique_order_per_certification"
            )
        ]

    def clean(self):
        # Validate at least one correct option exists
        if self.pk:  # Only validate on update
            correct_count = self.options.filter(is_correct=True).count()
            
            if correct_count == 0:
                raise ValidationError("At least one correct option is required.")
            
            if not self.is_multiple_correct and correct_count > 1:
                raise ValidationError(
                    "Only one correct option allowed for single-answer questions."
                )

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}"

    def get_correct_options(self):
        """Get list of correct option IDs"""
        return list(self.options.filter(is_correct=True).values_list('id', flat=True))

    def check_answer(self, selected_option_ids):
        """
        Check if the selected options are correct.
        Returns: (is_correct: bool, points_earned: int)
        """
        correct_ids = set(self.get_correct_options())
        selected_ids = set(selected_option_ids)
        
        if self.is_multiple_correct:
            # For multiple correct: all correct options must be selected, no extras
            is_correct = selected_ids == correct_ids
        else:
            # For single correct: exactly one option must be selected and it must be correct
            is_correct = len(selected_ids) == 1 and selected_ids.issubset(correct_ids)
        
        return is_correct, self.weight if is_correct else 0


class CertificationOption(models.Model):
    question = models.ForeignKey(
        CertificationQuestion,
        on_delete=models.CASCADE,
        related_name="options"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(
        default=False,
        help_text="Mark as correct answer"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Certification Option"
        verbose_name_plural = "Certification Options"

    def __str__(self):
        return self.text


class CertificationQuestionBank(models.Model):
    """
    Link table between Certification and Question Bank.
    Allows importing questions from the bank into certifications.
    """
    certification = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="bank_questions"
    )
    question = models.ForeignKey(
        'QuestionBank',
        on_delete=models.CASCADE,
        related_name="used_in_certifications"
    )
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Weight/points for this question in this certification"
    )
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order in the certification"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive questions are not shown to students"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Certification Question Bank Link"
        verbose_name_plural = "Certification Question Bank Links"
        constraints = [
            models.UniqueConstraint(
                fields=["certification", "question"],
                name="unique_question_per_certification"
            ),
            models.UniqueConstraint(
                fields=["certification", "order"],
                name="unique_order_per_certification_bank"
            )
        ]

    def __str__(self):
        return f"Q{self.order}: {self.question.text[:50]} (Cert: {self.certification.title})"

    def get_correct_options(self):
        """Get list of correct option IDs from the linked question"""
        return self.question.get_correct_options()

    def check_answer(self, selected_option_ids):
        """
        Check if the selected options are correct.
        Returns: (is_correct: bool, points_earned: int)
        """
        correct_ids = set(self.get_correct_options())
        selected_ids = set(selected_option_ids)

        if self.question.is_multiple_correct:
            # For multiple correct: all correct options must be selected, no extras
            is_correct = selected_ids == correct_ids
        else:
            # For single correct: exactly one option must be selected and it must be correct
            is_correct = len(selected_ids) == 1 and selected_ids.issubset(correct_ids)

        return is_correct, self.weight if is_correct else 0


class CertificationAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="certification_attempts"
    )
    certification = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="attempts"
    )
    score = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Final score as percentage"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    passed = models.BooleanField(default=False)
    attempt_number = models.PositiveSmallIntegerField()
    certificate_issued = models.BooleanField(default=False)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Certification Attempt"
        verbose_name_plural = "Certification Attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["certification", "user", "attempt_number"],
                name="unique_attempt_number"
            )
        ]
        indexes = [
            models.Index(fields=['user', 'certification']),
            models.Index(fields=['completed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - Attempt {self.attempt_number} - {self.certification.title}"

    def is_expired(self):
        """Check if attempt has exceeded time limit"""
        if self.completed_at:
            return False
        from datetime import timedelta
        time_limit = timedelta(minutes=self.certification.duration_minutes)
        return timezone.now() > (self.started_at + time_limit)

    def time_remaining(self):
        """Get remaining time in minutes"""
        if self.completed_at:
            return 0
        from datetime import timedelta
        time_limit = timedelta(minutes=self.certification.duration_minutes)
        expires_at = self.started_at + time_limit
        remaining = expires_at - timezone.now()
        return max(0, int(remaining.total_seconds() / 60))

    def calculate_score(self):
        """
        Calculate score based on submitted answers.
        Handles both manual questions and Question Bank questions.
        Returns: (score_percentage, total_points_earned, max_points)
        """
        total_earned = 0
        max_possible = 0

        # Calculate score for manual questions (old system)
        questions = self.certification.questions.filter(is_active=True)

        for question in questions:
            max_possible += question.weight

            # Get user's answer for this question
            try:
                answer = self.answers.get(question=question)
                is_correct, points = question.check_answer(answer.selected_options)
                total_earned += points
            except AttemptAnswer.DoesNotExist:
                # Question not answered
                continue

        # Calculate score for Question Bank questions (new system)
        bank_questions = self.certification.bank_questions.filter(is_active=True)

        for cert_question in bank_questions:
            max_possible += cert_question.weight

            # Get user's answer for this question
            try:
                answer = self.bank_answers.get(cert_question=cert_question)
                is_correct, points = cert_question.check_answer(answer.selected_options)
                total_earned += points
            except AttemptAnswerBank.DoesNotExist:
                # Question not answered
                continue

        score_percentage = int((total_earned / max_possible) * 100) if max_possible > 0 else 0
        return score_percentage, total_earned, max_possible

    def submit_and_grade(self):
        """
        Complete the attempt and calculate final score.
        Returns: dict with results
        """
        if self.completed_at:
            return {
                'error': 'Attempt already completed',
                'score': self.score,
                'passed': self.passed
            }
        
        if self.is_expired():
            self.score = 0
            self.passed = False
            self.completed_at = timezone.now()
            self.save()
            return {
                'error': 'Time limit exceeded',
                'score': 0,
                'passed': False
            }
        
        score, earned, maximum = self.calculate_score()
        self.score = score
        self.passed = score >= self.certification.passing_score
        self.completed_at = timezone.now()
        self.save()
        
        return {
            'score': score,
            'passed': self.passed,
            'points_earned': earned,
            'max_points': maximum,
            'passing_score': self.certification.passing_score
        }


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(
        CertificationAttempt,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    question = models.ForeignKey(
        CertificationQuestion,
        on_delete=models.CASCADE,
        related_name="given_answers"
    )
    selected_options = models.JSONField(
        help_text="List of selected option IDs"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "Attempt Answer"
        verbose_name_plural = "Attempt Answers"
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_question"
            )
        ]

    def clean(self):
        # Validate selected options belong to the question
        if not isinstance(self.selected_options, list):
            raise ValidationError("selected_options must be a list")
        
        valid_ids = list(self.question.options.values_list("id", flat=True))
        
        for opt_id in self.selected_options:
            if opt_id not in valid_ids:
                raise ValidationError(
                    f"Invalid option {opt_id} for question {self.question.id}"
                )
        
        # Validate single vs multiple selection
        if not self.question.is_multiple_correct and len(self.selected_options) > 1:
            raise ValidationError(
                f"Question {self.question.id} only allows one answer"
            )

    def __str__(self):
        return f"Attempt {self.attempt.id} - Q{self.question.order}"

    def is_correct(self):
        """Check if this answer is correct"""
        is_correct, _ = self.question.check_answer(self.selected_options)
        return is_correct

    def get_selected_texts(self):
        """Get text of selected options"""
        return list(
            self.question.options.filter(
                id__in=self.selected_options
            ).values_list('text', flat=True)
        )


class AttemptAnswerBank(models.Model):
    """
    Store student answers for Question Bank questions in certification attempts.
    Separate from AttemptAnswer to handle Question Bank questions.
    """
    attempt = models.ForeignKey(
        CertificationAttempt,
        on_delete=models.CASCADE,
        related_name="bank_answers"
    )
    cert_question = models.ForeignKey(
        CertificationQuestionBank,
        on_delete=models.CASCADE,
        related_name="given_answers"
    )
    selected_options = models.JSONField(
        help_text="List of selected option IDs from QuestionBankOption"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "Attempt Answer (Bank)"
        verbose_name_plural = "Attempt Answers (Bank)"
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "cert_question"],
                name="unique_bank_answer_per_question"
            )
        ]

    def clean(self):
        # Validate selected options belong to the question
        if not isinstance(self.selected_options, list):
            raise ValidationError("selected_options must be a list")

        question = self.cert_question.question
        valid_ids = list(question.options.values_list("id", flat=True))

        for opt_id in self.selected_options:
            if opt_id not in valid_ids:
                raise ValidationError(
                    f"Invalid option {opt_id} for question {question.id}"
                )

        # Validate single vs multiple selection
        if not question.is_multiple_correct and len(self.selected_options) > 1:
            raise ValidationError(
                f"Question {question.id} only allows one answer"
            )

    def __str__(self):
        return f"Attempt {self.attempt.id} - Bank Q{self.cert_question.order}"

    def is_correct(self):
        """Check if this answer is correct"""
        is_correct, _ = self.cert_question.check_answer(self.selected_options)
        return is_correct

    def get_selected_texts(self):
        """Get text of selected options"""
        question = self.cert_question.question
        return list(
            question.options.filter(
                id__in=self.selected_options
            ).values_list('text', flat=True)
        )


# ==========================
# QUESTION BANK MODELS
# ==========================

class QuestionBankCategory(models.Model):
    """Categories for organizing questions in the bank"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='question_categories',
        help_text="Optional: Link category to a specific course"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'question_bank_categories'
        ordering = ['name']
        verbose_name = 'Question Bank Category'
        verbose_name_plural = 'Question Bank Categories'

    def __str__(self):
        return self.name

    def get_question_count(self):
        return self.questions.filter(is_active=True).count()


class QuestionBank(models.Model):
    """Central question bank for storing reusable questions"""

    DIFFICULTY_CHOICES = [
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    ]

    SOURCE_CHOICES = [
        ('MANUAL', 'Manually Created'),
        ('AI_GENERATED', 'AI Generated'),
        ('IMPORTED', 'Imported'),
    ]

    text = models.TextField(help_text="The question text")
    explanation = models.TextField(
        blank=True,
        null=True,
        help_text="Optional explanation for the correct answer"
    )
    is_multiple_correct = models.BooleanField(
        default=False,
        help_text="True if multiple options can be correct"
    )
    difficulty = models.CharField(
        max_length=10,
        choices=DIFFICULTY_CHOICES,
        default='MEDIUM',
        help_text="Difficulty level of the question"
    )
    category = models.ForeignKey(
        'QuestionBankCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='questions',
        help_text="Category for organizing questions"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_questions',
        help_text="Optional: Link question to a specific course"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags for filtering questions (e.g., ['python', 'loops', 'basics'])"
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='MANUAL',
        help_text="How this question was created"
    )
    ai_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="The prompt used to generate this question (if AI generated)"
    )
    ai_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="The AI model used to generate this question"
    )
    weight = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Default weight/points for this question (1-10)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive questions are not available for use"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_bank_questions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'question_bank'
        ordering = ['-created_at']
        verbose_name = 'Question Bank Item'
        verbose_name_plural = 'Question Bank Items'
        indexes = [
            models.Index(fields=['difficulty', 'is_active']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['source', 'is_active']),
        ]

    def __str__(self):
        return f"{self.text[:50]}..." if len(self.text) > 50 else self.text

    def get_correct_options(self):
        """Get list of correct option IDs"""
        return list(self.options.filter(is_correct=True).values_list('id', flat=True))

    def get_options_count(self):
        return self.options.count()

    def get_correct_count(self):
        return self.options.filter(is_correct=True).count()


class QuestionBankOption(models.Model):
    """Options/answers for question bank questions"""
    question = models.ForeignKey(
        QuestionBank,
        on_delete=models.CASCADE,
        related_name='options'
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(
        default=False,
        help_text="Mark as correct answer"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of the option"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'question_bank_options'
        ordering = ['order', 'id']
        verbose_name = 'Question Bank Option'
        verbose_name_plural = 'Question Bank Options'

    def __str__(self):
        return f"{self.text[:30]}{'...' if len(self.text) > 30 else ''} ({'Correct' if self.is_correct else 'Incorrect'})"


class AIGenerationLog(models.Model):
    """Log of AI question generation requests"""

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    DIFFICULTY_CHOICES = QuestionBank.DIFFICULTY_CHOICES

    prompt = models.TextField(help_text="The prompt sent to the AI")
    topic = models.CharField(max_length=200, help_text="Topic for question generation")
    difficulty = models.CharField(
        max_length=10,
        choices=DIFFICULTY_CHOICES,
        default='MEDIUM'
    )
    num_questions = models.PositiveIntegerField(
        default=5,
        help_text="Number of questions requested"
    )
    model_used = models.CharField(
        max_length=100,
        help_text="AI model used for generation"
    )
    provider = models.CharField(
        max_length=50,
        default='OPENROUTER',
        help_text="AI provider used (OpenRouter, Gemini, Z.AI)"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    response_raw = models.TextField(
        blank=True,
        null=True,
        help_text="Raw response from the AI"
    )
    questions_created = models.PositiveIntegerField(
        default=0,
        help_text="Number of questions successfully created"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if generation failed"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_generation_logs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ai_generation_logs'
        ordering = ['-created_at']
        verbose_name = 'AI Generation Log'
        verbose_name_plural = 'AI Generation Logs'

    def __str__(self):
        return f"AI Gen: {self.topic} ({self.status}) - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class AIProviderSettings(models.Model):
    """Settings for AI providers (OpenRouter, Gemini, Z.AI)"""

    PROVIDER_CHOICES = [
        ('OPENROUTER', 'OpenRouter'),
        ('GEMINI', 'Google Gemini'),
        ('ZAI', 'Z.AI'),
    ]

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        unique=True,
        help_text="AI provider name"
    )
    api_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="API key for the provider (stored securely)"
    )
    api_endpoint = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Custom API endpoint (optional)"
    )
    default_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Default model to use for this provider"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether this provider is currently active"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default provider for AI generation"
    )
    max_tokens = models.PositiveIntegerField(
        default=4000,
        help_text="Maximum tokens for API requests"
    )
    temperature = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text="Temperature for AI generation (0.0-2.0)"
    )
    additional_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional provider-specific settings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_ai_settings'
    )

    class Meta:
        db_table = 'ai_provider_settings'
        ordering = ['provider', '-updated_at']
        verbose_name = 'AI Provider Settings'
        verbose_name_plural = 'AI Provider Settings'

    def __str__(self):
        return f"{self.get_provider_display()} ({'Active' if self.is_active else 'Inactive'})"

    def save(self, *args, **kwargs):
        if self.is_default:
            AIProviderSettings.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default_provider(cls):
        """Get the default active provider"""
        return cls.objects.filter(is_default=True, is_active=True).first()

    @classmethod
    def get_active_providers(cls):
        """Get all active providers"""
        return cls.objects.filter(is_active=True)

    def get_masked_api_key(self):
        """Return masked API key for display"""
        if not self.api_key:
            return None
        if len(self.api_key) <= 8:
            return '*' * len(self.api_key)
        return self.api_key[:4] + '*' * (len(self.api_key) - 8) + self.api_key[-4:]