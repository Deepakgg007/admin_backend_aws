# company/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q, Count, Avg
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Company, Concept, ConceptChallenge, Job
from .serializers import (
    CompanySerializer, ConceptSerializer, ConceptListSerializer,
    ConceptChallengeSerializer, JobSerializer, JobListSerializer
)
from api.permissions import IsStaffOrReadOnly


class CompanyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Company model
    Provides CRUD operations and custom actions
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        queryset = Company.objects.select_related('college', 'college__organization').all()

        # First, try to get college from JWT token (for college login)
        from college.views import get_college_id_from_token
        college_id = get_college_id_from_token(self.request)

        if college_id:
            # College admin authenticated via college login - see only their college's companies
            from api.models import College
            try:
                college = College.objects.get(college_id=college_id)
                print(f"COLLEGE LOGIN FILTER: Showing companies for college: {college.name}")
                queryset = queryset.filter(college=college)
                # Apply additional filters and return early
                return self._apply_query_filters(queryset)
            except College.DoesNotExist:
                pass

        # Fallback to user-based filtering
        user = self.request.user

        if user.is_authenticated:
            # Admin/Superuser - see all companies
            if user.is_superuser:
                pass  # No filtering, see all
            # College staff (has college but is staff) - see only their college's companies
            elif user.is_staff and hasattr(user, 'college') and user.college:
                queryset = queryset.filter(college=user.college)
            # Regular students - see their college's companies + global companies
            elif hasattr(user, 'college') and user.college:
                print(f"FILTER: Student - Filtering by college: {user.college.name} + Global")
                queryset = queryset.filter(
                    Q(college=user.college) | Q(college__isnull=True)
                )
            else:
                print("FILTER: Authenticated user with no college - No filtering")

        return self._apply_query_filters(queryset)

    def _apply_query_filters(self, queryset):
        """Apply common query parameter filters"""
        # Filter by college (for admin use)
        college_id = self.request.query_params.get('college')
        if college_id:
            queryset = queryset.filter(college_id=college_id)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Filter by hiring status
        is_hiring = self.request.query_params.get('is_hiring')
        if is_hiring is not None:
            queryset = queryset.filter(is_hiring=is_hiring.lower() == 'true')

        # Search by name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(industry__icontains=search)
            )

        return queryset.order_by('-is_hiring', '-created_at')

    def perform_create(self, serializer):
        """
        Automatically assign college when college staff creates a company.
        Supports both:
        1. College login (JWT token with college_id)
        2. Django admin users with college relationship
        """
        # First, try to get college from JWT token (for college login via /college/login/)
        from college.views import get_college_id_from_token
        college_id = get_college_id_from_token(self.request)

        if college_id:
            # College admin authenticated via college login
            from api.models import College
            try:
                college = College.objects.get(college_id=college_id)
                print(f"COLLEGE LOGIN: Auto-assigning company to college: {college.name}")
                serializer.save(college=college)
                return
            except College.DoesNotExist:
                print(f"ERROR: College with ID {college_id} not found")
                pass

        # Fallback to user-based logic for Django admin users
        user = self.request.user

        if user.is_authenticated:
            # If college staff (has college and is staff but not superuser), auto-assign their college
            if user.is_staff and hasattr(user, 'college') and user.college and not user.is_superuser:
                print(f"USER-BASED: Auto-assigning company to college: {user.college.name}")
                serializer.save(college=user.college)
            # Admin/Superuser can manually set college or leave it null for global companies
            else:
                print(f"ADMIN/SUPERUSER: Creating company (college can be null or manually set)")
                serializer.save()
        else:
            # No authentication found
            serializer.save()

    @extend_schema(
        summary="Get all concepts for this company",
        responses={200: ConceptListSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def concepts(self, request, slug=None):
        """Get all concepts for a specific company"""
        company = self.get_object()
        concepts = company.concepts.filter(is_active=True).order_by('order', 'name')
        serializer = ConceptListSerializer(concepts, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get statistics for this company",
        responses={200: dict}
    )
    @action(detail=True, methods=['get'])
    def statistics(self, request, slug=None):
        """Get company statistics"""
        company = self.get_object()
        stats = {
            'total_concepts': company.get_total_concepts(),
            'total_challenges': company.get_total_challenges(),
            'total_submissions': company.submissions.count() if hasattr(company, 'submissions') else 0,
            'total_participants': company.submissions.values('user').distinct().count() if hasattr(company, 'submissions') else 0,
            'is_hiring_open': company.is_hiring_open,
            'days_until_hiring_ends': company.days_until_hiring_ends,
        }
        return Response(stats)

    @extend_schema(
        summary="Get my college companies (College Staff only)",
        responses={200: CompanySerializer(many=True)}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_college_companies(self, request):
        """Get all companies created by my college (College Staff only)"""
        # First, try to get college from JWT token (for college login)
        from college.views import get_college_id_from_token
        from api.models import College

        college_id = get_college_id_from_token(request)

        if college_id:
            # College admin authenticated via college login
            try:
                college = College.objects.get(college_id=college_id)
                companies = Company.objects.filter(college=college).select_related('college', 'college__organization')
                serializer = self.get_serializer(companies, many=True)

                return Response({
                    'college_id': str(college.college_id),
                    'college_name': college.name,
                    'organization': college.organization.name,
                    'total_companies': companies.count(),
                    'companies': serializer.data
                })
            except College.DoesNotExist:
                return Response(
                    {'error': 'College not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Fallback to user-based logic
        user = request.user

        # Check if user is college staff
        if not user.is_staff or not hasattr(user, 'college') or not user.college:
            return Response(
                {'error': 'Only college staff can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get companies for this college only
        companies = Company.objects.filter(college=user.college).select_related('college', 'college__organization')

        serializer = self.get_serializer(companies, many=True)

        return Response({
            'college_id': user.college.id,
            'college_name': user.college.name,
            'organization': user.college.organization.name,
            'total_companies': companies.count(),
            'companies': serializer.data
        })

    @extend_schema(
        summary="Get companies grouped by college (Admin only)",
        responses={200: dict}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def by_college(self, request):
        """Get all companies grouped by college (Admin only) - see which college added which companies"""
        from api.models import College

        colleges = College.objects.prefetch_related('companies').filter(companies__isnull=False).distinct()

        result = []
        for college in colleges:
            companies_data = self.get_serializer(college.companies.all(), many=True).data
            result.append({
                'college_id': college.id,
                'college_name': college.name,
                'organization': college.organization.name,
                'total_companies': college.companies.count(),
                'companies': companies_data
            })

        # Also include companies without a college (global companies)
        global_companies = Company.objects.filter(college__isnull=True)
        if global_companies.exists():
            result.append({
                'college_id': None,
                'college_name': 'Global (No College)',
                'organization': 'System',
                'total_companies': global_companies.count(),
                'companies': self.get_serializer(global_companies, many=True).data
            })

        return Response(result)


class ConceptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Concept model
    """
    queryset = Concept.objects.all()
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return ConceptListSerializer
        return ConceptSerializer

    def get_queryset(self):
        queryset = Concept.objects.select_related('company').all()

        # Filter by company
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        # Filter by difficulty
        difficulty = self.request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset.order_by('company', 'order', 'name')

    @extend_schema(
        summary="Get all challenges for this concept",
        responses={200: ConceptChallengeSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def challenges(self, request, slug=None):
        """Get all challenges for a specific concept"""
        concept = self.get_object()
        # Filter out concept challenges where the linked challenge doesn't exist
        challenges = concept.challenges.filter(
            is_active=True,
            challenge__isnull=False
        ).select_related('challenge').order_by('order')
        serializer = ConceptChallengeSerializer(challenges, many=True)
        data = serializer.data

        # Add submission status for authenticated users
        if request.user.is_authenticated:
            from student.models import CompanyChallengeSubmission
            from django.db.models import Max

            # Get company from concept
            company = concept.company

            # Get challenge slugs from nested challenge_details
            challenge_slugs = []
            for c in data:
                challenge_details = c.get('challenge_details', {})
                if challenge_details and 'slug' in challenge_details:
                    challenge_slugs.append(challenge_details['slug'])

            # Get latest submission timestamp for each challenge
            latest_submissions = CompanyChallengeSubmission.objects.filter(
                user=request.user,
                company_id=company.id,
                concept_id=concept.id,
                challenge_slug__in=challenge_slugs
            ).values('challenge_slug').annotate(
                latest_submitted_at=Max('submitted_at')
            )

            # Get the actual submission data for those latest submissions
            submission_map = {}
            for item in latest_submissions:
                challenge_slug = item['challenge_slug']
                latest_sub = CompanyChallengeSubmission.objects.filter(
                    user=request.user,
                    company_id=company.id,
                    concept_id=concept.id,
                    challenge_slug=challenge_slug,
                    submitted_at=item['latest_submitted_at']
                ).values('status', 'score').first()

                if latest_sub:
                    submission_map[challenge_slug] = latest_sub

            # Add submission status to each ConceptChallenge (root level)
            for concept_challenge in data:
                challenge_details = concept_challenge.get('challenge_details', {})
                challenge_slug = challenge_details.get('slug')

                if challenge_slug and challenge_slug in submission_map:
                    sub = submission_map[challenge_slug]
                    # Add to challenge_details so frontend can access it
                    challenge_details['submission_status'] = sub['status']
                    challenge_details['submission_score'] = sub['score']
                else:
                    challenge_details['submission_status'] = None
                    challenge_details['submission_score'] = 0

        return Response(data)


class ConceptChallengeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ConceptChallenge model
    Links challenges to concepts with custom settings
    """
    queryset = ConceptChallenge.objects.all()
    serializer_class = ConceptChallengeSerializer
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        queryset = ConceptChallenge.objects.select_related(
            'concept', 'concept__company', 'challenge'
        ).all()

        # Filter by concept
        concept_id = self.request.query_params.get('concept')
        if concept_id:
            queryset = queryset.filter(concept_id=concept_id)

        # Filter by company
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(concept__company_id=company_id)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset.order_by('concept', 'order')


class JobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Job model
    Provides CRUD operations for job postings
    """
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        return JobSerializer

    def get_queryset(self):
        queryset = Job.objects.select_related('company', 'company__college').all()

        # First, try to get college from JWT token (for college login)
        from college.views import get_college_id_from_token
        college_id = get_college_id_from_token(self.request)

        if college_id:
            # College admin authenticated via college login - see only their college's companies' jobs
            from api.models import College
            try:
                college = College.objects.get(college_id=college_id)
                print(f"COLLEGE LOGIN FILTER: Showing jobs for companies from college: {college.name}")
                queryset = queryset.filter(company__college=college)
                return self._apply_query_filters(queryset)
            except College.DoesNotExist:
                pass

        # Fallback to user-based filtering
        user = self.request.user

        if user.is_authenticated:
            # Admin/Superuser - see all jobs
            if user.is_superuser:
                pass  # No filtering, see all
            # College staff - see only their college's companies' jobs
            elif user.is_staff and hasattr(user, 'college') and user.college:
                queryset = queryset.filter(company__college=user.college)
            # Regular students - see their college's companies' jobs + global companies' jobs
            elif hasattr(user, 'college') and user.college:
                queryset = queryset.filter(
                    Q(company__college=user.college) | Q(company__college__isnull=True)
                )

        return self._apply_query_filters(queryset)

    def _apply_query_filters(self, queryset):
        """Apply common query parameter filters"""
        # Filter by company
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        # Filter by job type
        job_type = self.request.query_params.get('job_type')
        if job_type:
            queryset = queryset.filter(job_type=job_type)

        # Filter by experience level
        experience_level = self.request.query_params.get('experience_level')
        if experience_level:
            queryset = queryset.filter(experience_level=experience_level)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Filter by featured
        is_featured = self.request.query_params.get('is_featured')
        if is_featured is not None:
            queryset = queryset.filter(is_featured=is_featured.lower() == 'true')

        # Search by title, description, location
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(location__icontains=search) |
                Q(company__name__icontains=search)
            )

        return queryset.order_by('-is_featured', '-created_at')

    def perform_create(self, serializer):
        """
        Automatically assign company validation and set added_by
        Optimized to avoid database locks with single atomic transaction
        """
        from django.db import transaction
        from rest_framework.exceptions import PermissionDenied
        from college.views import get_college_id_from_token
        from api.models import College

        company_id = self.request.data.get('company')

        # Wrap everything in a single atomic transaction
        with transaction.atomic():
            college_id = get_college_id_from_token(self.request)

            if college_id:
                # College admin authenticated via college login
                try:
                    college = College.objects.select_related('organization').get(college_id=college_id)
                    # Use exists() instead of get() to avoid locking
                    if not Company.objects.filter(id=company_id, college=college).exists():
                        raise PermissionDenied("You can only add jobs for companies from your college")

                    print(f"COLLEGE LOGIN: Adding job for company ID: {company_id}")
                    serializer.save(added_by=None)
                    return
                except College.DoesNotExist:
                    raise PermissionDenied("College not found")

            # Fallback to user-based logic
            user = self.request.user

            if user.is_authenticated:
                # If college staff, validate company belongs to their college
                if user.is_staff and hasattr(user, 'college') and user.college and not user.is_superuser:
                    if not Company.objects.filter(id=company_id, college=user.college).exists():
                        raise PermissionDenied("You can only add jobs for companies from your college")

                    print(f"USER-BASED: Adding job for company ID: {company_id}")
                    serializer.save(added_by=user)
                # Admin/Superuser can add jobs for any company
                else:
                    print(f"ADMIN/SUPERUSER: Adding job")
                    serializer.save(added_by=user)
            else:
                serializer.save()

    @extend_schema(
        summary="Get jobs for my college's companies",
        responses={200: JobListSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_college_jobs(self, request):
        """Get all jobs for companies from the logged-in college"""
        from college.views import get_college_id_from_token
        college_id = get_college_id_from_token(request)

        if college_id:
            from api.models import College
            try:
                college = College.objects.get(college_id=college_id)
                jobs = Job.objects.filter(company__college=college, is_active=True).select_related('company')
                serializer = JobListSerializer(jobs, many=True, context={'request': request})

                return Response({
                    'success': True,
                    'college_name': college.name,
                    'total_jobs': jobs.count(),
                    'jobs': serializer.data
                })
            except College.DoesNotExist:
                pass

        # Fallback for user-based
        user = request.user
        if hasattr(user, 'college') and user.college:
            jobs = Job.objects.filter(company__college=user.college, is_active=True).select_related('company')
            serializer = JobListSerializer(jobs, many=True, context={'request': request})

            return Response({
                'success': True,
                'college_name': user.college.name,
                'total_jobs': jobs.count(),
                'jobs': serializer.data
            })

        return Response({
            'success': False,
            'message': 'No college associated with this account'
        }, status=status.HTTP_400_BAD_REQUEST)
