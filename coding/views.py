
# coding/views.py

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import (
    Challenge, StarterCode, TestCase
)
from .serializers import (
    ChallengeListSerializer, ChallengeDetailSerializer,
    StarterCodeSerializer, TestCaseSerializer, TestCasePublicSerializer
)


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


