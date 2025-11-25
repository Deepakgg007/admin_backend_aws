# company/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.utils import timezone
from coding.models import Challenge

User = get_user_model()


def validate_youtube_url(value):
    """Validate YouTube URL format"""
    import re
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    if not re.match(youtube_regex, value):
        raise ValidationError('Enter a valid YouTube URL.')
    return value


class Company(models.Model):
    """
    Model representing companies that offer coding challenges/hiring tests
    Companies are automatically visible to students of the college that added them
    """
    name = models.CharField(max_length=255, unique=True, verbose_name="Company Name")
    slug = models.SlugField(unique=True, blank=True)
    image = models.ImageField(upload_to='company_images/', verbose_name="Company Logo", blank=True, null=True)
    description = models.TextField(verbose_name="Company Description", blank=True, null=True)

    # College relationship - who added this company
    # Companies without a college are visible to all students (legacy support)
    college = models.ForeignKey('api.College', on_delete=models.CASCADE, null=True, blank=True, related_name='companies', verbose_name="Added by College")

    # Hiring period
    hiring_period_start = models.DateField(verbose_name="Hiring Period Start", blank=True, null=True)
    hiring_period_end = models.DateField(verbose_name="Hiring Period End", blank=True, null=True)

    # Additional company details
    website = models.URLField(verbose_name="Company Website", blank=True, null=True)
    location = models.CharField(max_length=255, verbose_name="Company Location", blank=True, null=True)
    industry = models.CharField(max_length=255, verbose_name="Industry", blank=True, null=True)
    employee_count = models.CharField(max_length=50, verbose_name="Employee Count", blank=True, null=True)
    email = models.EmailField(verbose_name="Company Email", blank=True, null=True)
    phone = models.CharField(max_length=20, verbose_name="Phone Number", blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    is_hiring = models.BooleanField(default=False, verbose_name="Currently Hiring")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies'
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        # Auto-determine hiring status based on dates
        if self.hiring_period_start and self.hiring_period_end:
            today = timezone.now().date()
            self.is_hiring = self.hiring_period_start <= today <= self.hiring_period_end

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def is_hiring_open(self):
        """Check if hiring period is currently active"""
        if not self.hiring_period_start or not self.hiring_period_end:
            return False
        today = timezone.now().date()
        return self.hiring_period_start <= today <= self.hiring_period_end

    @property
    def days_until_hiring_ends(self):
        """Calculate days remaining in hiring period"""
        if not self.hiring_period_end or not self.is_hiring_open:
            return 0
        today = timezone.now().date()
        return (self.hiring_period_end - today).days

    def get_total_concepts(self):
        """Get total number of concepts for this company"""
        return self.concepts.count()

    def get_total_challenges(self):
        """Get total number of challenges across all concepts"""
        return Challenge.objects.filter(concept_links__concept__company=self).distinct().count()


class Concept(models.Model):
    """
    Model representing different coding concepts/topics within a company's challenge set
    Each concept groups related challenges together
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='concepts')
    name = models.CharField(max_length=255, verbose_name="Concept Name")
    slug = models.SlugField(blank=True)
    description = models.TextField(verbose_name="Concept Description", blank=True, null=True)

    # Concept metadata
    difficulty_level = models.CharField(max_length=20, choices=[
        ('BEGINNER', 'Beginner'),
        ('INTERMEDIATE', 'Intermediate'),
        ('ADVANCED', 'Advanced'),
        ('EXPERT', 'Expert'),
    ], default='INTERMEDIATE')

    estimated_time_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Estimated Time (minutes)",
        help_text="Estimated time to complete all challenges in this concept"
    )

    # Ordering and visibility
    order = models.PositiveIntegerField(default=0, verbose_name="Display Order")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'concepts'
        verbose_name = "Concept"
        verbose_name_plural = "Concepts"
        ordering = ['company', 'order', 'name']
        unique_together = ('company', 'name')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.company.name}-{self.name}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company.name} - {self.name}"

    def get_challenges(self):
        """Get all challenges for this concept"""
        return self.challenges.filter(is_active=True).order_by('order')

    def get_challenge_count(self):
        """Get total number of active challenges in this concept"""
        return self.challenges.filter(is_active=True).count()

    def get_max_score(self):
        """Get maximum possible score for this concept"""
        total_score = 0
        for concept_challenge in self.challenges.filter(is_active=True):
            total_score += concept_challenge.weighted_max_score
        return total_score


class ConceptChallenge(models.Model):
    """
    Model linking challenges to concepts with additional metadata
    """
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name='challenges')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='concept_links')

    # Ordering and customization for this specific concept
    order = models.PositiveIntegerField(default=0, verbose_name="Order in Concept")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    weight = models.FloatField(default=1.0, verbose_name="Score Weight",
                              help_text="Multiplier for challenge score in this concept")

    # Custom settings for this concept-challenge combination
    custom_time_limit = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name="Custom Time Limit (seconds)",
        help_text="Override default challenge time limit for this concept"
    )

    # Hint video fields
    hint_video_file = models.FileField(
        upload_to='company_challenge_hints/',
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'mkv'])],
        verbose_name="Hint Video File",
        blank=True,
        null=True,
        help_text="Upload a video file as hint (mp4, mov, avi, mkv)"
    )
    hint_youtube_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        validators=[validate_youtube_url],
        verbose_name="Hint YouTube URL",
        help_text="Enter a YouTube video URL as hint"
    )
    hint_video_title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Hint Video Title",
        help_text="Title for the hint video"
    )
    hint_video_description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Hint Video Description",
        help_text="Description for the hint video"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'concept_challenges'
        verbose_name = "Concept Challenge"
        verbose_name_plural = "Concept Challenges"
        ordering = ['concept', 'order', 'challenge__title']
        unique_together = ('concept', 'challenge')

    def __str__(self):
        return f"{self.concept.name} - {self.challenge.title}"

    @property
    def effective_time_limit(self):
        """Get the effective time limit for this challenge in this concept"""
        return self.custom_time_limit or self.challenge.time_limit_seconds

    @property
    def weighted_max_score(self):
        """Get the maximum score with weight applied"""
        return int(self.challenge.max_score * self.weight)

    def clean(self):
        """Validate that only one hint video option is provided"""
        if self.hint_video_file and self.hint_youtube_url:
            raise ValidationError('Please provide only one of hint video file or YouTube URL, not both.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def has_hint_video(self):
        """Check if this concept challenge has a hint video"""
        return bool(self.hint_video_file or self.hint_youtube_url)

    def get_youtube_embed_id(self):
        """Extract YouTube video ID from URL for embedding"""
        if self.hint_youtube_url:
            import re
            youtube_regex = re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)')
            match = youtube_regex.search(self.hint_youtube_url)
            if match:
                return match.group(1)
        return None

    def get_hint_video_display_title(self):
        """Get the title to display for the hint video"""
        return self.hint_video_title or f"Hint for {self.challenge.title}"


class Job(models.Model):
    """
    Model representing job postings by companies
    Jobs are linked to companies and visible to students of the college that added the company
    """
    JOB_TYPE_CHOICES = [
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('INTERNSHIP', 'Internship'),
        ('CONTRACT', 'Contract'),
        ('FREELANCE', 'Freelance'),
    ]

    EXPERIENCE_LEVEL_CHOICES = [
        ('ENTRY', 'Entry Level'),
        ('MID', 'Mid Level'),
        ('SENIOR', 'Senior Level'),
        ('LEAD', 'Lead/Manager'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='jobs', verbose_name="Company")
    title = models.CharField(max_length=255, verbose_name="Job Title")
    slug = models.SlugField(blank=True)
    description = models.TextField(verbose_name="Job Description")

    # Job details
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='FULL_TIME', verbose_name="Job Type")
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL_CHOICES, default='ENTRY', verbose_name="Experience Level")
    location = models.CharField(max_length=255, verbose_name="Job Location", blank=True, null=True)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Minimum Salary")
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Maximum Salary")
    salary_currency = models.CharField(max_length=10, default='INR', verbose_name="Currency")

    # Requirements
    required_skills = models.TextField(verbose_name="Required Skills", blank=True, null=True, help_text="Comma-separated list")
    qualifications = models.TextField(verbose_name="Qualifications", blank=True, null=True)
    responsibilities = models.TextField(verbose_name="Responsibilities", blank=True, null=True)

    # Application details
    application_deadline = models.DateTimeField(verbose_name="Application Deadline", blank=True, null=True)
    application_url = models.URLField(verbose_name="Application URL", blank=True, null=True)
    contact_email = models.EmailField(verbose_name="Contact Email", blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    is_featured = models.BooleanField(default=False, verbose_name="Featured Job")

    # College relationship - inherited from company
    # Jobs added by college admin can only be for companies they added
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='added_jobs', verbose_name="Added By")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jobs'
        verbose_name = "Job"
        verbose_name_plural = "Jobs"
        ordering = ['-created_at', '-is_featured']

    def save(self, *args, **kwargs):
        if not self.slug:
            import uuid

            # Generate base slug from company and title
            base_slug = slugify(f"{self.company.name}-{self.title}")

            # Use UUID for guaranteed uniqueness - NO database queries needed
            # This completely eliminates database lock issues
            unique_suffix = str(uuid.uuid4())[:8]
            self.slug = f"{base_slug}-{unique_suffix}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company.name} - {self.title}"

    @property
    def is_deadline_passed(self):
        """Check if application deadline has passed"""
        if not self.application_deadline:
            return False
        return timezone.now() > self.application_deadline

    @property
    def days_until_deadline(self):
        """Calculate days remaining until deadline"""
        if not self.application_deadline or self.is_deadline_passed:
            return 0
        return (self.application_deadline - timezone.now()).days
