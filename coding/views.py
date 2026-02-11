
# coding/views.py

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiTypes

from .models import (
    Challenge, StarterCode, TestCase, ALGORITHM_CATEGORIES
)
from .serializers import (
    ChallengeListSerializer, ChallengeDetailSerializer,
    StarterCodeSerializer, TestCaseSerializer, TestCasePublicSerializer,
    AICodingChallengeGenerateSerializer, DuplicateCheckSerializer
)
from .ai_generator import AICodingChallengeGenerator


@extend_schema_view(
    list=extend_schema(
        summary="List Challenges",
        description="Get list of all coding challenges with filtering and search",
        tags=["Coding Challenges"],
        parameters=[
            OpenApiParameter(name='difficulty', type=str, enum=['EASY', 'MEDIUM', 'HARD']),
            OpenApiParameter(name='category', type=str),
            OpenApiParameter(name='search', type=str, description='Search in title, description, tags'),
            OpenApiParameter(name='attempt_status', type=str, enum=['not_attempted', 'attempted', 'solved'], description='Filter by user attempt status'),
        ]
    ),
    retrieve=extend_schema(
        summary="Get Challenge Details",
        description="Get detailed information about a specific challenge including test cases and starter code",
        tags=["Coding Challenges"]
    ),
    create=extend_schema(
        summary="Create Challenge",
        description="Create a new coding challenge (Admin only)",
        tags=["Coding Challenges"]
    ),
    update=extend_schema(
        summary="Update Challenge",
        description="Update a coding challenge (Admin only)",
        tags=["Coding Challenges"]
    ),
    destroy=extend_schema(
        summary="Delete Challenge",
        description="Delete a coding challenge (Admin only)",
        tags=["Coding Challenges"]
    )
)
class ChallengeViewSet(viewsets.ModelViewSet):
    """Coding Challenges Management"""
    queryset = Challenge.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['difficulty', 'category']
    search_fields = ['title', 'description', 'tags']
    ordering_fields = ['created_at', 'difficulty', 'success_rate', 'total_submissions']
    ordering = ['-created_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return ChallengeListSerializer
        return ChallengeDetailSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticatedOrReadOnly()]

    def list(self, request, *args, **kwargs):
        """Override list to add attempt status filtering"""
        # Get attempt_status filter parameter
        attempt_status = request.query_params.get('attempt_status', '')

        if attempt_status and request.user.is_authenticated:
            from student.models import CodingChallengeSubmission

            queryset = self.get_queryset()

            if attempt_status == 'not_attempted':
                # Get challenges the user hasn't attempted
                attempted_challenges = CodingChallengeSubmission.objects.filter(
                    user=request.user
                ).values_list('challenge_id', flat=True)
                queryset = queryset.exclude(id__in=attempted_challenges)

            elif attempt_status == 'attempted':
                # Get challenges the user has attempted but not solved
                solved_challenges = CodingChallengeSubmission.objects.filter(
                    user=request.user,
                    status='ACCEPTED'
                ).values_list('challenge_id', flat=True)

                attempted_challenges = CodingChallengeSubmission.objects.filter(
                    user=request.user
                ).values_list('challenge_id', flat=True)

                queryset = queryset.filter(
                    id__in=attempted_challenges
                ).exclude(id__in=solved_challenges)

            elif attempt_status == 'solved':
                # Get challenges the user has solved
                solved_challenges = CodingChallengeSubmission.objects.filter(
                    user=request.user,
                    status='ACCEPTED'
                ).values_list('challenge_id', flat=True)
                queryset = queryset.filter(id__in=solved_challenges)

            # Update the queryset for this request
            self.queryset = queryset

        response = super().list(request, *args, **kwargs)
        return response

    @extend_schema(
        summary="Get Categories",
        description="Get all available challenge categories",
        tags=["Coding Challenges"],
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all available categories"""
        from .models import ALGORITHM_CATEGORIES
        return Response({
            'categories': [{'value': cat[0], 'label': cat[1]} for cat in ALGORITHM_CATEGORIES]
        })

    @extend_schema(
        summary="Get Difficulty Levels",
        description="Get all available difficulty levels",
        tags=["Coding Challenges"],
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'])
    def difficulties(self, request):
        """Get all difficulty levels"""
        return Response({
            'difficulties': [{'value': d[0], 'label': d[1]} for d in Challenge.DIFFICULTY_CHOICES]
        })

    @extend_schema(
        summary="Generate Coding Challenges with AI",
        description="Generate complete coding challenges using AI (OpenRouter, Gemini, Z.AI) with duplicate detection",
        tags=["Coding Challenges"],
        request=AICodingChallengeGenerateSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT
        }
    )
    @action(detail=False, methods=['post'], url_path='generate-with-ai')
    def generate_with_ai(self, request):
        """
        Generate coding challenges using AI with duplicate detection.

        POST /api/coding/challenges/generate-with-ai/
        {
            "topic": "Two Sum problem",
            "category": "arrays",
            "difficulty": "EASY",
            "num_challenges": 1,
            "additional_context": "Focus on hash map solution",
            "check_duplicates": true,
            "force_save": false
        }
        """
        serializer = AICodingChallengeGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Check user permission
        if not request.user.is_staff and not request.user.is_superuser:
            return Response(
                {'error': 'Only administrators can generate coding challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )

        generator = AICodingChallengeGenerator()

        result = generator.generate_challenges(
            topic=data['topic'],
            category=data['category'],
            difficulty=data['difficulty'],
            num_challenges=data['num_challenges'],
            additional_context=data.get('additional_context', ''),
            created_by=request.user,
            force_save=data.get('force_save', False),
            check_duplicates=data.get('check_duplicates', True)
        )

        if result.get('status') == 'success':
            return Response(result, status=status.HTTP_201_CREATED)
        elif result.get('status') == 'error':
            error_code = result.get('error', 'Unknown error')
            if 'rate limit' in error_code.lower():
                return Response(result, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Check for Duplicate Challenges",
        description="Check if a challenge is similar to existing ones before saving",
        tags=["Coding Challenges"],
        request=DuplicateCheckSerializer,
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['post'], url_path='check-duplicates')
    def check_duplicates(self, request):
        """
        Check for duplicate/similar challenges.

        POST /api/coding/challenges/check-duplicates/
        {
            "title": "Two Sum",
            "description": "Given an array of integers...",
            "test_cases": [
                {"input_data": "2 7 11 15\\n9", "expected_output": "0 1"}
            ],
            "exclude_id": 123  // Optional: exclude a specific challenge
        }
        """
        serializer = DuplicateCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from .ai_generator import DuplicateDetector

        detector = DuplicateDetector()
        report = detector.comprehensive_duplicate_check(
            title=serializer.validated_data['title'],
            description=serializer.validated_data['description'],
            test_cases=serializer.validated_data.get('test_cases', []),
            exclude_id=serializer.validated_data.get('exclude_id')
        )

        return Response(report)

    @extend_schema(
        summary="Get AI Provider Status",
        description="Check if AI provider is configured for coding challenge generation",
        tags=["Coding Challenges"],
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='ai-provider-status')
    def ai_provider_status(self, request):
        """Get the status of AI provider configuration"""
        from course_cert.models import AIProviderSettings

        # First try to get the default active provider with API key
        provider = AIProviderSettings.objects.filter(
            is_default=True,
            is_active=True
        ).exclude(api_key__isnull=True).exclude(api_key='').first()

        if not provider:
            # If no default, try to get any active provider with API key
            provider = AIProviderSettings.objects.filter(
                is_active=True
            ).exclude(api_key__isnull=True).exclude(api_key='').first()

        if not provider:
            active_providers = AIProviderSettings.objects.filter(is_active=True)
            providers_with_key = active_providers.exclude(api_key__isnull=True).exclude(api_key='')
            return Response({
                'has_provider': False,
                'has_any_provider': providers_with_key.exists(),
                'provider_count': providers_with_key.count(),
                'active_count': active_providers.count(),
                'message': 'No active AI provider with API key configured. Please configure one in AI Settings.'
            })

        return Response({
            'has_provider': True,
            'provider': provider.provider,
            'provider_display': provider.get_provider_display(),
            'model': provider.default_model,
            'is_active': provider.is_active,
            'is_default': provider.is_default,
            'has_api_key': bool(provider.api_key)
        })

    @extend_schema(
        summary="Get Companies for a Challenge",
        description="Get all companies that use this specific challenge",
        tags=["Coding Challenges"]
    )
    @action(detail=True, methods=['get'])
    def companies(self, request, slug=None):
        """
        Get all companies that use this specific challenge.

        Returns a list of companies that have this challenge
        linked through their concepts.
        """
        from company.models import Company

        challenge = self.get_object()

        # Get all companies that have this challenge through their concepts
        # A challenge can be used by multiple companies via ConceptChallenge
        companies = Company.objects.filter(
            concepts__concept_challenges__challenge=challenge
        ).distinct().order_by('name')

        # Use the CompanySerializer from company app
        from company.serializers import CompanySerializer
        serializer = CompanySerializer(companies, many=True)

        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List Starter Codes", tags=["Starter Code"]),
    retrieve=extend_schema(summary="Get Starter Code", tags=["Starter Code"]),
    create=extend_schema(summary="Create Starter Code (Admin)", tags=["Starter Code"]),
    update=extend_schema(summary="Update Starter Code (Admin)", tags=["Starter Code"]),
    destroy=extend_schema(summary="Delete Starter Code (Admin)", tags=["Starter Code"])
)
class StarterCodeViewSet(viewsets.ModelViewSet):
    """Starter Code Management"""
    queryset = StarterCode.objects.all()
    serializer_class = StarterCodeSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['challenge', 'language']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticatedOrReadOnly()]


@extend_schema_view(
    list=extend_schema(
        summary="List Test Cases",
        description="Get test cases (hidden test cases show '[Hidden]' for non-admin users)",
        tags=["Test Cases"]
    ),
    retrieve=extend_schema(summary="Get Test Case", tags=["Test Cases"]),
    create=extend_schema(summary="Create Test Case (Admin)", tags=["Test Cases"]),
    update=extend_schema(summary="Update Test Case (Admin)", tags=["Test Cases"]),
    destroy=extend_schema(summary="Delete Test Case (Admin)", tags=["Test Cases"])
)
class TestCaseViewSet(viewsets.ModelViewSet):
    """Test Case Management - Hidden test cases are protected from non-admin users"""
    queryset = TestCase.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['challenge', 'is_sample', 'hidden']

    def get_serializer_class(self):
        # For create/update actions, always use TestCaseSerializer (has challenge field)
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseSerializer

        # For read actions, admins see full data, users see public version (hidden data masked)
        if self.request.user and self.request.user.is_staff:
            return TestCaseSerializer
        return TestCasePublicSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticatedOrReadOnly()]


