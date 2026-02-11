# company/serializers.py

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Company, Concept, ConceptChallenge, Job
from coding.models import Challenge


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for Company model"""
    total_concepts = serializers.IntegerField(source='get_total_concepts', read_only=True)
    total_challenges = serializers.IntegerField(source='get_total_challenges', read_only=True)
    is_hiring_open = serializers.BooleanField(read_only=True)
    days_until_hiring_ends = serializers.IntegerField(read_only=True)
    college_name = serializers.CharField(source='college.name', read_only=True, allow_null=True)
    college_organization = serializers.CharField(source='college.organization.name', read_only=True, allow_null=True)
    image_display = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'slug', 'image', 'image_display', 'description',
            'college', 'college_name', 'college_organization',
            'hiring_period_start', 'hiring_period_end',
            'website', 'location', 'industry', 'employee_count',
            'email', 'phone',
            'is_active', 'is_hiring', 'is_hiring_open', 'days_until_hiring_ends',
            'total_concepts', 'total_challenges',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'is_hiring', 'created_at', 'updated_at', 'image_display']
        extra_kwargs = {
            'image': {'write_only': True, 'required': False, 'allow_null': True}
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_image_display(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def to_internal_value(self, data):
        # Handle image field - if it's a string "null" or "Null", treat it as None
        if 'image' in data:
            if data['image'] in ['null', 'Null', 'NULL', '', None]:
                data = data.copy()
                data.pop('image', None)
        return super().to_internal_value(data)


class ConceptListSerializer(serializers.ModelSerializer):
    """Minimal serializer for listing concepts"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    challenge_count = serializers.IntegerField(source='get_challenge_count', read_only=True)

    class Meta:
        model = Concept
        fields = [
            'id', 'company', 'company_name', 'name', 'slug',
            'difficulty_level', 'estimated_time_minutes',
            'order', 'is_active', 'challenge_count'
        ]
        read_only_fields = ['slug']


class ConceptSerializer(serializers.ModelSerializer):
    """Full serializer for Concept model"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    challenge_count = serializers.IntegerField(source='get_challenge_count', read_only=True)
    max_score = serializers.IntegerField(source='get_max_score', read_only=True)

    class Meta:
        model = Concept
        fields = [
            'id', 'company', 'company_name', 'name', 'slug', 'description',
            'difficulty_level', 'estimated_time_minutes',
            'order', 'is_active', 'challenge_count', 'max_score',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']


class ChallengeMinimalSerializer(serializers.ModelSerializer):
    """Minimal challenge serializer for nested use"""
    companies = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = ['id', 'title', 'slug', 'difficulty', 'max_score', 'category', 'companies']

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_companies(self, obj):
        """Get companies that use this challenge"""
        from .models import Company
        companies = Company.objects.filter(
            id__in=ConceptChallenge.objects.filter(challenge=obj).values_list('concept__company_id', flat=True)
        ).distinct().order_by('name')
        return CompanySerializer(companies, many=True).data


class ConceptChallengeSerializer(serializers.ModelSerializer):
    """Serializer for ConceptChallenge model"""
    challenge_details = ChallengeMinimalSerializer(source='challenge', read_only=True)
    concept_name = serializers.CharField(source='concept.name', read_only=True)
    effective_time_limit = serializers.IntegerField(read_only=True)
    weighted_max_score = serializers.IntegerField(read_only=True)
    has_hint_video = serializers.BooleanField(read_only=True)
    youtube_embed_id = serializers.CharField(source='get_youtube_embed_id', read_only=True)

    class Meta:
        model = ConceptChallenge
        fields = [
            'id', 'concept', 'concept_name', 'challenge', 'challenge_details',
            'order', 'is_active', 'weight', 'custom_time_limit', 'effective_time_limit',
            'weighted_max_score', 'hint_video_file', 'hint_youtube_url',
            'hint_video_title', 'hint_video_description',
            'has_hint_video', 'youtube_embed_id', 'created_at'
        ]
        read_only_fields = ['created_at']


class JobSerializer(serializers.ModelSerializer):
    """Serializer for Job model"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_logo = serializers.SerializerMethodField()
    college_name = serializers.CharField(source='company.college.name', read_only=True, allow_null=True)
    is_deadline_passed = serializers.BooleanField(read_only=True)
    days_until_deadline = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'company', 'company_name', 'company_logo', 'college_name',
            'title', 'slug', 'description', 'job_type', 'experience_level',
            'location', 'salary_min', 'salary_max', 'salary_currency',
            'required_skills', 'qualifications', 'responsibilities',
            'application_deadline', 'application_url', 'contact_email',
            'is_active', 'is_featured', 'is_deadline_passed', 'days_until_deadline',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company_logo(self, obj):
        if obj.company and obj.company.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.company.image.url)
            return obj.company.image.url
        return None


class JobListSerializer(serializers.ModelSerializer):
    """Minimal serializer for listing jobs"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_logo = serializers.SerializerMethodField()
    college_name = serializers.CharField(source='company.college.name', read_only=True, allow_null=True)
    is_deadline_passed = serializers.BooleanField(read_only=True)
    days_until_deadline = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'company', 'company_name', 'company_logo', 'college_name',
            'title', 'slug', 'job_type', 'experience_level',
            'location', 'salary_min', 'salary_max', 'salary_currency',
            'application_deadline', 'is_active', 'is_featured',
            'is_deadline_passed', 'days_until_deadline', 'created_at'
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company_logo(self, obj):
        if obj.company and obj.company.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.company.image.url)
            return obj.company.image.url
        return None
