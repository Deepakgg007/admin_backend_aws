from rest_framework import serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from .models import StudentChallengeSubmission, ContentSubmission, ContentProgress
from .user_profile_models import UserProfile, Badge, UserBadge, UserActivity, LeaderboardCache
from coding.models import Challenge
from courses.models import TaskQuestion, TaskMCQ, TaskCoding

User = get_user_model()

class StudentChallengeSubmissionSerializer(serializers.ModelSerializer):
    challenge_title = serializers.CharField(source='challenge.title', read_only=True)
    challenge_slug = serializers.CharField(source='challenge.slug', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    language_display = serializers.CharField(source='get_language_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = StudentChallengeSubmission
        fields = [
            'id', 'user', 'user_username', 'challenge', 'challenge_title', 'challenge_slug',
            'submitted_code', 'language', 'language_display', 'status', 'status_display',
            'passed_tests', 'total_tests', 'score', 'runtime', 'memory_used',
            'test_results', 'compilation_message', 'is_best_submission', 'submitted_at'
        ]
        read_only_fields = ['user', 'status', 'passed_tests', 'total_tests', 'score',
                           'runtime', 'memory_used', 'test_results', 'compilation_message',
                           'is_best_submission', 'submitted_at']


class StudentChallengeSubmissionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating submissions"""
    class Meta:
        model = StudentChallengeSubmission
        fields = ['challenge', 'submitted_code', 'language']

    def validate_challenge(self, value):
        """Ensure challenge exists and is accessible"""
        if not Challenge.objects.filter(pk=value.pk).exists():
            raise serializers.ValidationError("Challenge not found")
        return value


class StudentChallengeSubmissionListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list view"""
    challenge_title = serializers.CharField(source='challenge.title', read_only=True)
    challenge_slug = serializers.CharField(source='challenge.slug', read_only=True)
    challenge_difficulty = serializers.CharField(source='challenge.difficulty', read_only=True)
    language_display = serializers.CharField(source='get_language_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = StudentChallengeSubmission
        fields = [
            'id', 'challenge', 'challenge_title', 'challenge_slug', 'challenge_difficulty',
            'language', 'language_display', 'status', 'status_display',
            'passed_tests', 'total_tests', 'score', 'runtime',
            'is_best_submission', 'submitted_at'
        ]


# ==================== Profile & Leaderboard Serializers ====================

class BadgeSerializer(serializers.ModelSerializer):
    """Serializer for Badge model"""
    class Meta:
        model = Badge
        fields = [
            'id', 'name', 'slug', 'description', 'icon', 'badge_type',
            'rarity', 'points_required', 'challenges_required', 
            'streak_required', 'bonus_points'
        ]


class UserBadgeSerializer(serializers.ModelSerializer):
    """Serializer for user-earned badges"""
    badge = BadgeSerializer(read_only=True)
    
    class Meta:
        model = UserBadge
        fields = ['id', 'badge', 'earned_at']


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info serializer"""
    college_name = serializers.SerializerMethodField()
    college_logo = serializers.SerializerMethodField()
    college_signature = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    college_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_picture', 'college_name', 'college_logo', 'college_signature', 'college_id', 'usn'
        ]

    def get_college_id(self, obj):
        return obj.college_id if obj.college_id else None

    def get_college_name(self, obj):
        return obj.get_college_display()

    def get_college_logo(self, obj):
        """Return full URL for college logo"""
        if obj.college and obj.college.logo:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.college.logo.url)
            return obj.college.logo.url
        return None

    def get_college_signature(self, obj):
        """Return full URL for college signature"""
        if obj.college and obj.college.signature:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.college.signature.url)
            return obj.college.signature.url
        return None

    def get_profile_picture(self, obj):
        """Return full URL for profile picture"""
        if obj.profile_picture:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None


class UserProfileSerializer(serializers.ModelSerializer):
    """Complete user profile serializer"""
    user = UserBasicSerializer(read_only=True)
    badges = serializers.SerializerMethodField()
    accuracy_percentage = serializers.FloatField(read_only=True)
    rank_badge = serializers.CharField(source='get_rank_badge', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'total_points', 'global_rank', 'college_rank',
            'challenges_solved', 'easy_solved', 'medium_solved', 'hard_solved',
            'company_challenges_solved', 'current_streak', 'longest_streak',
            'last_activity', 'total_submissions', 'successful_submissions',
            'accuracy_percentage', 'total_time_spent_minutes',
            'average_runtime_ms', 'average_memory_kb',
            'courses_enrolled', 'courses_completed', 'rank_badge',
            'badges', 'created_at', 'updated_at'
        ]
    
    def get_badges(self, obj):
        user_badges = UserBadge.objects.filter(user=obj.user).select_related('badge')[:10]
        return UserBadgeSerializer(user_badges, many=True).data


class UserProfileStatsSerializer(serializers.ModelSerializer):
    """Lightweight stats serializer"""
    username = serializers.CharField(source='user.username', read_only=True)
    rank_badge = serializers.CharField(source='get_rank_badge', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'username', 'total_points', 'global_rank', 'college_rank',
            'challenges_solved', 'current_streak', 'rank_badge'
        ]


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """Serializer for leaderboard entries"""
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    profile_picture = serializers.SerializerMethodField()
    college_name = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'user', 'username', 'first_name', 'last_name', 'profile_picture', 'college_name',
            'total_points', 'global_rank', 'college_rank',
            'challenges_solved', 'easy_solved', 'medium_solved', 'hard_solved',
            'current_streak'
        ]
    
    def get_college_name(self, obj):
        return obj.user.get_college_display()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_profile_picture(self, obj):
        if obj.user and obj.user.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.user.profile_picture.url)
            return obj.user.profile_picture.url
        return None


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity logs"""
    username = serializers.CharField(source='user.username', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'username', 'activity_type', 'activity_type_display',
            'activity_date', 'details', 'points_earned', 'timestamp'
        ]


class ProgressStatsSerializer(serializers.Serializer):
    """Custom serializer for progress statistics"""
    total_challenges = serializers.IntegerField()
    solved_challenges = serializers.IntegerField()
    easy_total = serializers.IntegerField()
    easy_solved = serializers.IntegerField()
    medium_total = serializers.IntegerField()
    medium_solved = serializers.IntegerField()
    hard_total = serializers.IntegerField()
    hard_solved = serializers.IntegerField()
    completion_percentage = serializers.FloatField()


class CourseProgressSerializer(serializers.Serializer):
    """Serializer for course-specific progress"""
    course_id = serializers.IntegerField()
    course_title = serializers.CharField()
    course_slug = serializers.CharField()
    total_challenges = serializers.IntegerField()
    solved_challenges = serializers.IntegerField()
    progress_percentage = serializers.FloatField()
    points_earned = serializers.IntegerField()



# ==================== Content Submission Serializers ====================

class ContentSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for content submissions"""
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)

    class Meta:
        model = ContentSubmission
        fields = [
            "id", "submission_id", "student", "student_name", "task", "task_title",
            "submission_type", "question", "document", "video", "page",
            "mcq_selected_choice", "code_submitted", "answer_text",
            "is_correct", "score", "completed",
            "submitted_at", "updated_at"
        ]
        read_only_fields = ["id", "submission_id", "student", "submitted_at", "updated_at"]


class MCQSubmissionSerializer(serializers.Serializer):
    """Serializer for MCQ question submissions"""
    question_id = serializers.IntegerField(required=True)
    selected_choice = serializers.IntegerField(required=True, min_value=1, max_value=4)

    def validate_question_id(self, value):
        """Validate question exists and is MCQ type"""
        try:
            question = TaskQuestion.objects.get(id=value)
            if question.question_type != "mcq":
                raise serializers.ValidationError("Question is not an MCQ")
            return value
        except TaskQuestion.DoesNotExist:
            raise serializers.ValidationError("Question not found")


class CodingSubmissionSerializer(serializers.Serializer):
    """Serializer for coding question submissions"""
    question_id = serializers.IntegerField(required=True)
    code = serializers.CharField(required=True, allow_blank=False)

    def validate_question_id(self, value):
        """Validate question exists and is coding type"""
        try:
            question = TaskQuestion.objects.get(id=value)
            if question.question_type != "coding":
                raise serializers.ValidationError("Question is not a coding question")
            return value
        except TaskQuestion.DoesNotExist:
            raise serializers.ValidationError("Question not found")


class ContentCompletionSerializer(serializers.Serializer):
    """Serializer for marking content as completed (documents, videos only)"""
    content_type = serializers.ChoiceField(
        choices=["document", "video"],
        required=True
    )
    content_id = serializers.IntegerField(required=True)


class MCQSubmissionResponseSerializer(serializers.Serializer):
    """Response serializer for MCQ submissions with feedback"""
    question_id = serializers.IntegerField()
    selected_choice = serializers.IntegerField()
    is_correct = serializers.BooleanField()
    correct_choices = serializers.ListField(child=serializers.IntegerField())
    solution_explanation = serializers.CharField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2)
    completed = serializers.BooleanField()
    submitted_at = serializers.DateTimeField()


# ============================================================================
# CONTENT PROGRESS SERIALIZERS (Videos, Documents, Questions - NO PAGES)
# ============================================================================

class ContentProgressSerializer(serializers.ModelSerializer):
    """Serializer for content progress tracking"""
    class Meta:
        model = ContentProgress
        fields = ['id', 'user', 'course', 'task', 'content_type', 'content_id', 'is_completed', 'completed_at', 'created_at']
        read_only_fields = ['user', 'completed_at', 'created_at']


class MarkContentCompleteSerializer(serializers.Serializer):
    """Serializer for marking content as completed (videos, documents, questions ONLY)"""
    content_type = serializers.ChoiceField(choices=['video', 'document', 'question'])
    content_id = serializers.IntegerField()
    task_id = serializers.IntegerField()
    course_id = serializers.IntegerField()

    def validate(self, data):
        """Validate that the content exists"""
        from courses.models import Task, TaskVideo, TaskDocument, TaskQuestion

        # Validate task exists
        try:
            task = Task.objects.get(id=data['task_id'])
            data['task'] = task
        except Task.DoesNotExist:
            raise serializers.ValidationError({"task_id": "Task not found"})

        # Validate content exists
        content_type = data['content_type']
        content_id = data['content_id']

        try:
            if content_type == 'video':
                TaskVideo.objects.get(id=content_id, task=task)
            elif content_type == 'document':
                TaskDocument.objects.get(id=content_id, task=task)
            elif content_type == 'question':
                TaskQuestion.objects.get(id=content_id, task=task)
        except (TaskVideo.DoesNotExist, TaskDocument.DoesNotExist, TaskQuestion.DoesNotExist):
            raise serializers.ValidationError({content_type: f"{content_type.capitalize()} not found"})

        return data


class CourseProgressSummarySerializer(serializers.Serializer):
    """Serializer for course progress summary"""
    completed_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    percentage = serializers.FloatField()
    course_id = serializers.IntegerField()
    course_title = serializers.CharField()

