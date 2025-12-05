from django.db import models
from django.conf import settings
import uuid


class University(models.Model):
    university_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField()
    logo = models.ImageField(upload_to='university_logos/', blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_universities')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'universities'
        ordering = ['name']
        verbose_name_plural = 'Universities'

    def __str__(self):
        return self.name


class Organization(models.Model):
    organization_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='organizations')
    name = models.CharField(max_length=255)
    address = models.TextField()
    logo = models.ImageField(upload_to='organization_logos/', blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_organizations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']
        unique_together = ['university', 'name']

    def __str__(self):
        return f"{self.name} - {self.university.name}"


class College(models.Model):
    college_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='colleges')
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    address = models.TextField()
    phone_number = models.CharField(max_length=20)
    max_students = models.IntegerField(default=0, help_text="Maximum number of students that can register")
    current_students = models.IntegerField(default=0, help_text="Current number of registered students")
    logo = models.ImageField(upload_to='college_logos/', blank=True, null=True)
    signature = models.ImageField(upload_to='college_signatures/', blank=True, null=True, help_text="College signature image")
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_colleges')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'colleges'
        ordering = ['name']
        unique_together = ['organization', 'name']

    def __str__(self):
        return f"{self.name} - {self.organization.name}"

    @property
    def available_seats(self):
        return self.max_students - self.current_students

    @property
    def is_registration_open(self):
        return self.current_students < self.max_students

    def check_password(self, raw_password):
        """Check if the provided password matches the stored password"""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)


