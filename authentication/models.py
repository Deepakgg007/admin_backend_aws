from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class CustomUser(AbstractUser):
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    usn = models.CharField(max_length=20, blank=True, null=True, unique=True, help_text="University Serial Number")
    college = models.ForeignKey('api.College', on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    college_name = models.CharField(max_length=255, blank=True, null=True, help_text="College name if not in system")

    # Approval System
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        help_text="Student approval status by college"
    )
    approved_by = models.ForeignKey(
        'api.College',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_students',
        help_text="College that approved/rejected this student"
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection if applicable")
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def get_college_display(self):
        """Returns college name from relationship or manual entry"""
        if self.college:
            return self.college.name
        return self.college_name or "No college specified"


class OTP(models.Model):
    """Model to store OTP codes for password reset"""
    OTP_TYPE_CHOICES = [
        ('user', 'User'),
        ('college', 'College'),
    ]

    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=10, choices=OTP_TYPE_CHOICES)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'otps'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'otp_type', 'is_verified']),
        ]

    def __str__(self):
        return f"{self.email} - {self.otp_code} ({self.otp_type})"

    def is_expired(self):
        """Check if OTP has expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @classmethod
    def cleanup_expired(cls):
        """Delete expired OTPs"""
        from django.utils import timezone
        cls.objects.filter(expires_at__lt=timezone.now()).delete()
