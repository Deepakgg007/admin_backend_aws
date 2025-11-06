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
    college = models.ForeignKey(
        'api.College',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certifications',
        help_text="If set, only students from this college can access this certification"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Certification"
        verbose_name_plural = "Certifications"
        indexes = [
            models.Index(fields=['college', 'is_active']),
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
        college_info = f" [{self.college.name}]" if self.college else " [Global]"
        return f"{self.title} - {self.course.title}{college_info}"

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

    def can_user_attempt(self, user):
        """Check if user can start a new attempt"""
        # Check college restriction
        if self.college:
            if not hasattr(user, 'student_profile') or user.student_profile.college != self.college:
                return False, "This certification is only available to students from a specific college"
        
        # Check enrollment
        if not Enrollment.objects.filter(
            student=user,
            course=self.course,
            status='active'
        ).exists():
            return False, "Not enrolled in this course"
        
        # Check incomplete attempts
        if self.attempts.filter(
            user=user,
            completed_at__isnull=True
        ).exists():
            return False, "You have an incomplete attempt"
        
        # Check max attempts
        attempts_count = self.attempts.filter(user=user).count()
        if attempts_count >= self.max_attempts:
            return False, "Maximum attempts reached"
        
        return True, "Can attempt"

    def is_accessible_by_user(self, user):
        """Check if user can access this certification based on college restriction"""
        if not self.college:
            # Global certification - accessible to all enrolled students
            return True
        
        # College-specific certification - check if user belongs to the college
        if hasattr(user, 'student_profile'):
            return user.student_profile.college == self.college
        
        return False


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
        Returns: (score_percentage, total_points_earned, max_points)
        """
        total_earned = 0
        max_possible = 0
        
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