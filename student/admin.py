from django.contrib import admin
from .models import CodingChallengeSubmission, CompanyChallengeSubmission, ContentSubmission, ContentProgress

@admin.register(CodingChallengeSubmission)
class CodingChallengeSubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'challenge', 'language', 'status', 'score', 'passed_tests', 'total_tests', 'submitted_at']
    list_filter = ['status', 'language', 'submitted_at', 'is_best_submission']
    search_fields = ['user__username', 'user__email', 'challenge__title']
    readonly_fields = ['submitted_at']
    ordering = ['-submitted_at']

    fieldsets = (
        ('Submission Info', {
            'fields': ('user', 'challenge', 'language', 'submitted_code')
        }),
        ('Results', {
            'fields': ('status', 'passed_tests', 'total_tests', 'score', 'runtime', 'memory_used', 'is_best_submission')
        }),
        ('Details', {
            'fields': ('test_results', 'compilation_message', 'submitted_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CompanyChallengeSubmission)
class CompanyChallengeSubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'company_name', 'concept_name', 'challenge_title', 'language', 'status', 'score', 'passed_tests', 'total_tests', 'submitted_at']
    list_filter = ['status', 'language', 'submitted_at', 'is_best_submission', 'company_name']
    search_fields = ['user__username', 'user__email', 'challenge_title', 'company_name', 'concept_name']
    readonly_fields = ['submitted_at']
    ordering = ['-submitted_at']

    fieldsets = (
        ('Company/Concept Info', {
            'fields': ('company_id', 'company_name', 'concept_id', 'concept_name')
        }),
        ('Challenge Info', {
            'fields': ('challenge_id', 'challenge_slug', 'challenge_title', 'language', 'submitted_code')
        }),
        ('Submission Info', {
            'fields': ('user', 'status', 'passed_tests', 'total_tests', 'score', 'runtime', 'memory_used', 'is_best_submission')
        }),
        ('Details', {
            'fields': ('test_results', 'compilation_message', 'submitted_at'),
            'classes': ('collapse',)
        }),
    )



@admin.register(ContentSubmission)
class ContentSubmissionAdmin(admin.ModelAdmin):
    list_display = ["student", "task", "submission_type", "get_content_ref", "is_correct", "score", "completed", "submitted_at"]
    list_filter = ["submission_type", "completed", "is_correct", "submitted_at"]
    search_fields = ["student__email", "task__title"]
    readonly_fields = ["submission_id", "submitted_at", "updated_at"]
    ordering = ["-submitted_at"]

    def get_content_ref(self, obj):
        if obj.question:
            return f"Q: {obj.question.question_text[:30]}..."
        elif obj.document:
            title = obj.document.title or "Untitled"
            return f"Doc: {title}"
        elif obj.video:
            title = obj.video.title or "Untitled"
            return f"Video: {title}"
        return "N/A"
    get_content_ref.short_description = "Content"


@admin.register(ContentProgress)
class ContentProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'task', 'content_type', 'content_id', 'is_completed', 'completed_at']
    list_filter = ['content_type', 'is_completed', 'completed_at']
    search_fields = ['user__email', 'user__username', 'course__title', 'task__title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-completed_at']

