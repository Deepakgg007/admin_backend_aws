
# coding/serializers.py

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Challenge, StarterCode, TestCase, ALGORITHM_CATEGORIES


class StarterCodeSerializer(serializers.ModelSerializer):
    """Serializer for starter code"""
    language_display = serializers.CharField(source='get_language_display', read_only=True)
    challenge = serializers.PrimaryKeyRelatedField(
        queryset=Challenge.objects.all(),
        error_messages={
            'required': 'Challenge ID is required',
            'does_not_exist': 'Challenge with ID {pk_value} does not exist'
        }
    )

    class Meta:
        model = StarterCode
        fields = ['id', 'challenge', 'language', 'language_display', 'code']
        read_only_fields = ['id']


class TestCaseSerializer(serializers.ModelSerializer):
    """Serializer for test cases"""
    challenge = serializers.PrimaryKeyRelatedField(
        queryset=Challenge.objects.all(),
        error_messages={
            'required': 'Challenge ID is required',
            'does_not_exist': 'Challenge with ID {pk_value} does not exist'
        }
    )

    class Meta:
        model = TestCase
        fields = [
            'id', 'challenge', 'input_data', 'expected_output',
            'is_sample', 'hidden', 'score_weight'
        ]
        read_only_fields = ['id']


class TestCasePublicSerializer(serializers.ModelSerializer):
    """Public serializer for test cases (hides data for hidden test cases)"""

    class Meta:
        model = TestCase
        fields = ['id', 'input_data', 'expected_output', 'is_sample', 'hidden']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Hide input and expected output for hidden test cases (only show to admins)
        if instance.hidden:
            data['expected_output'] = '[Hidden]'
            data['input_data'] = '[Hidden]'
        return data


class ChallengeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for challenge list view"""
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    tags_list = serializers.SerializerMethodField()
    is_solved = serializers.SerializerMethodField()
    is_attempted = serializers.SerializerMethodField()
    failed = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            'id', 'title', 'slug', 'difficulty', 'difficulty_display',
            'category', 'category_display', 'max_score', 'success_rate',
            'total_submissions', 'accepted_submissions', 'tags_list',
            'is_solved', 'is_attempted', 'failed',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at', 'is_solved', 'is_attempted', 'failed']

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_tags_list(self, obj):
        return obj.get_tags_list()

    @extend_schema_field(serializers.BooleanField())
    def get_is_solved(self, obj):
        """Check if challenge is solved by the authenticated user"""
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False

        # Check if user has accepted submission for this challenge
        return obj.coding_submissions.filter(
            user=request.user,
            status='ACCEPTED'
        ).exists()

    @extend_schema_field(serializers.BooleanField())
    def get_is_attempted(self, obj):
        """Check if challenge is attempted by the authenticated user"""
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False

        # Check if user has any submission (attempted) for this challenge
        return obj.coding_submissions.filter(
            user=request.user
        ).exists()

    @extend_schema_field(serializers.BooleanField())
    def get_failed(self, obj):
        """Check if user has failed attempts (attempted but not solved)"""
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False

        # User has failed if they attempted but don't have accepted submission
        has_attempt = obj.coding_submissions.filter(
            user=request.user
        ).exists()

        has_accepted = obj.coding_submissions.filter(
            user=request.user,
            status='ACCEPTED'
        ).exists()

        return has_attempt and not has_accepted


class ChallengeDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for challenge detail view"""
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    tags_list = serializers.SerializerMethodField()
    starter_codes = StarterCodeSerializer(many=True, read_only=True)
    test_cases = serializers.SerializerMethodField()
    total_test_cases = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            'id', 'title', 'slug', 'description', 'input_format',
            'output_format', 'constraints', 'explanation',
            'sample_input', 'sample_output', 'time_complexity',
            'space_complexity', 'difficulty', 'difficulty_display',
            'max_score', 'category', 'category_display', 'tags', 'tags_list',
            'time_limit_seconds', 'memory_limit_mb', 'success_rate',
            'total_submissions', 'accepted_submissions', 'starter_codes',
            'test_cases', 'total_test_cases', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'success_rate', 'total_submissions',
                           'accepted_submissions', 'created_at', 'updated_at']

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_tags_list(self, obj):
        return obj.get_tags_list()

    def get_test_cases(self, obj):
        """Return test cases based on user role - admins see full data, users see masked data"""
        request = self.context.get('request')
        test_cases = obj.test_cases.all()

        # If user is staff/admin, show full test case data
        if request and request.user and request.user.is_staff:
            return TestCaseSerializer(test_cases, many=True).data
        # Otherwise, show public version (hidden data masked)
        return TestCasePublicSerializer(test_cases, many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_total_test_cases(self, obj):
        return obj.test_cases.count()


# ==========================
# AI Generation Serializers
# ==========================

class AICodingChallengeGenerateSerializer(serializers.Serializer):
    """Serializer for AI coding challenge generation request"""
    topic = serializers.CharField(
        max_length=500,
        help_text="Topic for the coding challenge (e.g., 'Two Sum', 'Binary Tree Traversal')"
    )
    category = serializers.ChoiceField(
        choices=ALGORITHM_CATEGORIES,
        default='implementation',
        help_text="Algorithm category"
    )
    difficulty = serializers.ChoiceField(
        choices=['EASY', 'MEDIUM', 'HARD'],
        default='MEDIUM',
        help_text="Difficulty level"
    )
    num_challenges = serializers.IntegerField(
        default=1,
        min_value=1,
        max_value=5,
        help_text="Number of challenges to generate (max 5)"
    )
    additional_context = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Additional context for generation"
    )
    check_duplicates = serializers.BooleanField(
        default=True,
        help_text="Whether to check for duplicate challenges"
    )
    force_save = serializers.BooleanField(
        default=False,
        help_text="Save even if duplicates are found"
    )


class DuplicateCheckSerializer(serializers.Serializer):
    """Serializer for duplicate check request"""
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    test_cases = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True
    )
    exclude_id = serializers.IntegerField(required=False, allow_null=True)


