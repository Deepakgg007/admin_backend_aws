"""
Django Models for Video Proctoring System
==========================================

Stores proctoring sessions, violations, and analytics data.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
import json


class ProctoringSession(models.Model):
    """Stores a complete proctoring session for a quiz attempt"""

    SESSION_STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated (Violation)'),
        ('interrupted', 'Interrupted'),
    ]

    # Identifiers
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # References
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='proctoring_sessions'
    )
    task = models.ForeignKey(
        'courses.Task',
        on_delete=models.CASCADE,
        related_name='proctoring_sessions',
        null=True,
        blank=True
    )

    # Session info
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default='active')

    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Statistics
    total_frames = models.PositiveIntegerField(default=0)
    face_present_frames = models.PositiveIntegerField(default=0)
    face_absent_frames = models.PositiveIntegerField(default=0)
    multiple_face_frames = models.PositiveIntegerField(default=0)
    look_away_frames = models.PositiveIntegerField(default=0)

    # Risk score (0-100, higher = more suspicious)
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    # Summary
    violation_count = models.PositiveIntegerField(default=0)
    high_severity_count = models.PositiveIntegerField(default=0)
    medium_severity_count = models.PositiveIntegerField(default=0)
    low_severity_count = models.PositiveIntegerField(default=0)

    # Raw data (JSON)
    session_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'proctoring_sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['student', 'task']),
            models.Index(fields=['status']),
            models.Index(fields=['risk_score']),
        ]

    def __str__(self):
        return f"Proctoring Session - {self.student.email} - {self.started_at}"

    @property
    def duration_seconds(self):
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    def calculate_risk_score(self):
        """Calculate and update risk score based on violations"""
        score = 0.0

        # Weight violations by severity
        score += self.high_severity_count * 20
        score += self.medium_severity_count * 10
        score += self.low_severity_count * 5

        # Factor in face absence
        if self.total_frames > 0:
            absent_ratio = self.face_absent_frames / self.total_frames
            score += absent_ratio * 30

            multi_face_ratio = self.multiple_face_frames / self.total_frames
            score += multi_face_ratio * 40

            look_away_ratio = self.look_away_frames / self.total_frames
            score += look_away_ratio * 20

        self.risk_score = min(100.0, score)
        self.save(update_fields=['risk_score'])
        return self.risk_score

    def get_summary(self):
        """Return session summary as dict"""
        return {
            'session_id': str(self.session_id),
            'student_id': self.student.id,
            'task_id': str(self.task.task_id) if self.task else None,
            'status': self.status,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_seconds': self.duration_seconds,
            'total_frames': self.total_frames,
            'statistics': {
                'face_present_percentage': (self.face_present_frames / max(1, self.total_frames)) * 100,
                'face_absent_percentage': (self.face_absent_frames / max(1, self.total_frames)) * 100,
                'multiple_face_percentage': (self.multiple_face_frames / max(1, self.total_frames)) * 100,
                'look_away_percentage': (self.look_away_frames / max(1, self.total_frames)) * 100,
            },
            'violation_summary': {
                'total': self.violation_count,
                'high': self.high_severity_count,
                'medium': self.medium_severity_count,
                'low': self.low_severity_count,
            },
            'risk_score': float(self.risk_score),
        }


class ProctoringViolation(models.Model):
    """Individual violation events during proctoring"""

    VIOLATION_TYPES = [
        ('face_not_detected', 'Face Not Detected'),
        ('multiple_faces_detected', 'Multiple Faces Detected'),
        ('prolonged_look_away', 'Prolonged Look Away'),
        ('suspicious_gaze_pattern', 'Suspicious Gaze Pattern'),
        ('suspicious_object_detected', 'Suspicious Object Detected'),
        ('face_mismatch', 'Face Mismatch (Different Person)'),
        ('tab_switch', 'Tab/Window Switch'),
        ('fullscreen_exit', 'Fullscreen Exit'),
        ('copy_paste_attempt', 'Copy/Paste Attempt'),
    ]

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    # Identifiers
    violation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Reference to session
    session = models.ForeignKey(
        ProctoringSession,
        on_delete=models.CASCADE,
        related_name='violations'
    )

    # Violation details
    violation_type = models.CharField(max_length=50, choices=VIOLATION_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='low')
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=0.0)

    # Timing
    timestamp = models.DateTimeField(auto_now_add=True)
    frame_number = models.PositiveIntegerField(default=0)

    # Additional data
    details = models.JSONField(default=dict, blank=True)

    # Screenshot evidence (optional)
    screenshot = models.ImageField(
        upload_to='proctoring_evidence/',
        blank=True,
        null=True,
        help_text="Screenshot at time of violation"
    )

    # Review status
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_violations'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, null=True)
    is_false_positive = models.BooleanField(default=False)

    class Meta:
        db_table = 'proctoring_violations'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
            models.Index(fields=['violation_type']),
            models.Index(fields=['severity']),
            models.Index(fields=['reviewed']),
        ]

    def __str__(self):
        return f"{self.get_violation_type_display()} - {self.severity} - {self.timestamp}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update session violation counts
        self.session.violation_count = self.session.violations.count()
        self.session.high_severity_count = self.session.violations.filter(severity='high').count()
        self.session.medium_severity_count = self.session.violations.filter(severity='medium').count()
        self.session.low_severity_count = self.session.violations.filter(severity='low').count()
        self.session.save()
        self.session.calculate_risk_score()


class ProctoringFrame(models.Model):
    """Optional: Store individual frame data for detailed analysis"""

    session = models.ForeignKey(
        ProctoringSession,
        on_delete=models.CASCADE,
        related_name='frames'
    )

    frame_number = models.PositiveIntegerField()
    timestamp = models.DateTimeField()

    # Detection results
    faces_detected = models.PositiveIntegerField(default=0)
    face_bbox = models.JSONField(default=dict, blank=True)
    looking_at_screen = models.BooleanField(default=True)
    gaze_direction = models.CharField(max_length=20, default='center')
    suspicious_objects = models.JSONField(default=list, blank=True)

    # Frame image (optional - can be large)
    frame_image = models.ImageField(
        upload_to='proctoring_frames/',
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'proctoring_frames'
        ordering = ['frame_number']
        unique_together = ['session', 'frame_number']
        indexes = [
            models.Index(fields=['session', 'frame_number']),
        ]


class ProctoringSettings(models.Model):
    """Configurable proctoring settings per task/college"""

    # Reference - can be global or task-specific
    task = models.OneToOneField(
        'courses.Task',
        on_delete=models.CASCADE,
        related_name='proctoring_settings',
        null=True,
        blank=True
    )
    college = models.ForeignKey(
        'api.College',
        on_delete=models.CASCADE,
        related_name='proctoring_settings',
        null=True,
        blank=True
    )

    # Feature toggles
    face_detection_enabled = models.BooleanField(default=True)
    gaze_detection_enabled = models.BooleanField(default=True)
    object_detection_enabled = models.BooleanField(default=False)  # Requires more resources
    face_verification_enabled = models.BooleanField(default=False)

    # Thresholds
    max_absent_frames = models.PositiveIntegerField(
        default=30,
        help_text="Max consecutive frames without face before violation"
    )
    max_multiple_face_frames = models.PositiveIntegerField(
        default=15,
        help_text="Max consecutive frames with multiple faces before violation"
    )
    max_look_away_frames = models.PositiveIntegerField(
        default=60,
        help_text="Max consecutive frames looking away before violation"
    )

    # Confidence thresholds
    min_face_confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.50)
    min_object_confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.50)
    face_similarity_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=0.60)

    # Actions
    auto_terminate_on_high_severity = models.BooleanField(
        default=False,
        help_text="Automatically terminate quiz on high severity violation"
    )
    auto_terminate_threshold = models.PositiveIntegerField(
        default=3,
        help_text="Number of high severity violations before auto-terminate"
    )

    # Screenshot settings
    capture_screenshots = models.BooleanField(default=True)
    capture_interval_frames = models.PositiveIntegerField(default=30)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'proctoring_settings'

    def __str__(self):
        if self.task:
            return f"Proctoring Settings - {self.task.title}"
        return f"Proctoring Settings - College: {self.college.name if self.college else 'Global'}"

    def to_detector_config(self):
        """Convert to VideoCheatingDetector config format"""
        return {
            'face_detection': {
                'enabled': self.face_detection_enabled,
                'min_confidence': float(self.min_face_confidence),
                'max_absent_frames': self.max_absent_frames,
                'max_multiple_face_frames': self.max_multiple_face_frames,
            },
            'gaze_detection': {
                'enabled': self.gaze_detection_enabled,
                'max_look_away_frames': self.max_look_away_frames,
            },
            'object_detection': {
                'enabled': self.object_detection_enabled,
                'min_confidence': float(self.min_object_confidence),
            },
            'face_verification': {
                'enabled': self.face_verification_enabled,
                'similarity_threshold': float(self.face_similarity_threshold),
            },
            'alert_thresholds': {
                'face_absent_violation': self.max_absent_frames,
                'multiple_face_violation': self.max_multiple_face_frames,
                'look_away_violation': self.max_look_away_frames,
            }
        }
