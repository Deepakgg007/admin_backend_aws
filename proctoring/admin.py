"""
Django Admin Configuration for Proctoring System
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import ProctoringSession, ProctoringViolation, ProctoringSettings


class ProctoringViolationInline(admin.TabularInline):
    """Inline display of violations within session"""
    model = ProctoringViolation
    extra = 0
    readonly_fields = ['violation_type', 'severity', 'confidence', 'timestamp', 'frame_number', 'display_screenshot']
    fields = ['violation_type', 'severity', 'confidence', 'timestamp', 'frame_number', 'reviewed', 'is_false_positive']

    def display_screenshot(self, obj):
        if obj.screenshot:
            return format_html('<img src="{}" width="200" />', obj.screenshot.url)
        return "-"
    display_screenshot.short_description = "Screenshot"


@admin.register(ProctoringSession)
class ProctoringSessionAdmin(admin.ModelAdmin):
    """Admin interface for proctoring sessions"""

    list_display = [
        'session_id',
        'student_email',
        'task_title',
        'status',
        'risk_score',
        'violation_count',
        'started_at',
        'duration',
    ]
    list_filter = ['status', 'started_at']
    search_fields = ['student__email', 'task__title', 'session_id']
    readonly_fields = [
        'session_id',
        'started_at',
        'ended_at',
        'total_frames',
        'face_present_frames',
        'face_absent_frames',
        'multiple_face_frames',
        'look_away_frames',
        'risk_score',
    ]
    inlines = [ProctoringViolationInline]

    def student_email(self, obj):
        return obj.student.email
    student_email.short_description = 'Student'

    def task_title(self, obj):
        return obj.task.title if obj.task else '-'
    task_title.short_description = 'Task/Quiz'

    def duration(self, obj):
        if obj.duration_seconds:
            minutes = int(obj.duration_seconds // 60)
            seconds = int(obj.duration_seconds % 60)
            return f"{minutes}m {seconds}s"
        return "-"
    duration.short_description = 'Duration'

    actions = ['mark_as_reviewed', 'export_sessions']

    def mark_as_reviewed(self, request, queryset):
        count = 0
        for session in queryset:
            for violation in session.violations.filter(reviewed=False):
                violation.reviewed = True
                violation.reviewed_by = request.user
                violation.save()
                count += 1
        self.message_user(request, f"Marked {count} violations as reviewed.")
    mark_as_reviewed.short_description = "Mark all violations as reviewed"

    def export_sessions(self, request, queryset):
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="proctoring_sessions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Session ID', 'Student Email', 'Task', 'Status', 'Risk Score',
            'Violations', 'Started', 'Ended', 'Duration (s)'
        ])

        for session in queryset:
            writer.writerow([
                str(session.session_id),
                session.student.email,
                session.task.title if session.task else '',
                session.status,
                float(session.risk_score),
                session.violation_count,
                session.started_at,
                session.ended_at or '',
                session.duration_seconds or '',
            ])

        return response
    export_sessions.short_description = "Export sessions to CSV"


@admin.register(ProctoringViolation)
class ProctoringViolationAdmin(admin.ModelAdmin):
    """Admin interface for violations"""

    list_display = [
        'violation_id',
        'session_link',
        'violation_type',
        'severity',
        'confidence',
        'reviewed',
        'is_false_positive',
        'timestamp',
    ]
    list_filter = ['violation_type', 'severity', 'reviewed', 'is_false_positive', 'timestamp']
    search_fields = ['session__session_id', 'session__student__email']
    readonly_fields = [
        'violation_id',
        'session',
        'violation_type',
        'severity',
        'confidence',
        'timestamp',
        'frame_number',
        'details',
        'display_screenshot',
    ]
    actions = ['mark_reviewed', 'mark_false_positive', 'mark_valid']

    def session_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:proctoring_proctoringsession_change', args=[obj.session.pk])
        return format_html('<a href="{}">{}</a>', url, obj.session.session_id)
    session_link.short_description = 'Session'

    def display_screenshot(self, obj):
        if obj.screenshot:
            return format_html('<img src="{}" width="400" />', obj.screenshot.url)
        return "No screenshot"
    display_screenshot.short_description = "Screenshot"

    def mark_reviewed(self, request, queryset):
        updated = queryset.update(reviewed=True, reviewed_by=request.user)
        self.message_user(request, f"Marked {updated} violations as reviewed.")
    mark_reviewed.short_description = "Mark as reviewed"

    def mark_false_positive(self, request, queryset):
        updated = queryset.update(
            reviewed=True,
            reviewed_by=request.user,
            is_false_positive=True
        )
        self.message_user(request, f"Marked {updated} violations as false positives.")
    mark_false_positive.short_description = "Mark as false positive"

    def mark_valid(self, request, queryset):
        updated = queryset.update(
            reviewed=True,
            reviewed_by=request.user,
            is_false_positive=False
        )
        self.message_user(request, f"Marked {updated} violations as valid.")
    mark_valid.short_description = "Mark as valid violation"


@admin.register(ProctoringSettings)
class ProctoringSettingsAdmin(admin.ModelAdmin):
    """Admin interface for proctoring settings"""

    list_display = [
        'id',
        'task_title',
        'college_name',
        'face_detection_enabled',
        'gaze_detection_enabled',
        'auto_terminate_on_high_severity',
    ]
    list_filter = [
        'face_detection_enabled',
        'gaze_detection_enabled',
        'object_detection_enabled',
        'auto_terminate_on_high_severity',
    ]
    search_fields = ['task__title', 'college__name']

    fieldsets = (
        ('Reference', {
            'fields': ('task', 'college')
        }),
        ('Detection Features', {
            'fields': (
                'face_detection_enabled',
                'gaze_detection_enabled',
                'object_detection_enabled',
                'face_verification_enabled',
            )
        }),
        ('Thresholds', {
            'fields': (
                'max_absent_frames',
                'max_multiple_face_frames',
                'max_look_away_frames',
                'min_face_confidence',
                'min_object_confidence',
                'face_similarity_threshold',
            )
        }),
        ('Actions', {
            'fields': (
                'auto_terminate_on_high_severity',
                'auto_terminate_threshold',
            )
        }),
        ('Screenshot Settings', {
            'fields': (
                'capture_screenshots',
                'capture_interval_frames',
            )
        }),
    )

    def task_title(self, obj):
        return obj.task.title if obj.task else '-'
    task_title.short_description = 'Task'

    def college_name(self, obj):
        return obj.college.name if obj.college else 'Global'
    college_name.short_description = 'College'
