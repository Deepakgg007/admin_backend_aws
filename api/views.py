from rest_framework import generics, status, viewsets, filters, mixins
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from django.contrib.auth import get_user_model
from django.db.models import Q, Count, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from drf_spectacular.utils import extend_schema, OpenApiResponse
import requests
import base64
import logging

from .models import University, Organization, College
from .serializers import (
    UniversitySerializer, OrganizationSerializer,
    CollegeSerializer, CollegeListSerializer
)
from .permissions import IsOwnerOrReadOnly, IsAdminUserOrReadOnly
from .utils import StandardResponseMixin, CustomPagination

User = get_user_model()
logger = logging.getLogger(__name__)


class APIRootView(APIView, StandardResponseMixin):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="API Root",
        description="Get information about available API endpoints",
        responses={
            200: OpenApiResponse(description='API endpoint information')
        }
    )
    def get(self, request):
        return self.success_response(
            data={
                'version': '1.0.0',
                'endpoints': {
                    'authentication': '/api/auth/',
                    'college': '/api/college/',
                    'docs': {
                        'swagger': '/api/docs/',
                        'redoc': '/api/redoc/',
                    },
                    'universities': '/api/universities/',
                    'organizations': '/api/organizations/',
                    'colleges': '/api/colleges/',
                    'courses': '/api/courses/',
                }
            },
            message="Welcome to Z1 Solution API"
        )

api_root = APIRootView.as_view()


class UniversityViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    pagination_class = CustomPagination

    @extend_schema(tags=['Institutions - Universities'])

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="University created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="University updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="University deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="University retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Universities retrieved successfully."
        )

    @action(detail=True, methods=['get'])
    def organizations(self, request, pk=None):
        university = self.get_object()
        organizations = university.organizations.filter(is_active=True)
        serializer = OrganizationSerializer(organizations, many=True)
        return self.success_response(
            data=serializer.data,
            message="Organizations retrieved successfully."
        )

    @action(detail=True, methods=['get'])
    def colleges(self, request, pk=None):
        university = self.get_object()
        colleges = College.objects.filter(
            organization__university=university,
            is_active=True
        )
        serializer = CollegeListSerializer(colleges, many=True)
        return self.success_response(
            data=serializer.data,
            message="Colleges retrieved successfully."
        )

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        university = self.get_object()
        university.is_active = False
        university.save()
        return self.success_response(
            message="University deactivated successfully."
        )


class OrganizationViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'university__name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    pagination_class = CustomPagination

    @extend_schema(tags=['Organizations'])

    def get_queryset(self):
        queryset = super().get_queryset()
        university_id = self.request.query_params.get('university')
        if university_id:
            queryset = queryset.filter(university_id=university_id)
        return queryset.select_related('university', 'created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="Organization created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="Organization updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="Organization deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Organization retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Organizations retrieved successfully."
        )

    @action(detail=True, methods=['get'])
    def colleges(self, request, pk=None):
        organization = self.get_object()
        colleges = organization.colleges.filter(is_active=True)
        serializer = CollegeListSerializer(colleges, many=True)
        return self.success_response(
            data=serializer.data,
            message="Colleges retrieved successfully."
        )

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        organization = self.get_object()
        organization.is_active = False
        organization.save()
        return self.success_response(
            message="Organization deactivated successfully."
        )


class CollegeViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    queryset = College.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'organization__name', 'organization__university__name']
    ordering_fields = ['name', 'created_at', 'max_students']
    ordering = ['name']
    pagination_class = CustomPagination

    @extend_schema(tags=['Colleges'])

    def get_serializer_class(self):
        if self.action == 'list':
            return CollegeListSerializer
        return CollegeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by organization
        organization_id = self.request.query_params.get('organization')
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)

        # Filter by university
        university_id = self.request.query_params.get('university')
        if university_id:
            queryset = queryset.filter(organization__university_id=university_id)

        # Filter by registration status
        registration_open = self.request.query_params.get('registration_open')
        if registration_open == 'true':
            queryset = queryset.filter(current_students__lt=F('max_students'))

        return queryset.select_related('organization__university', 'created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(
            data=serializer.data,
            message="College created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=serializer.data,
            message="College updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(
            message="College deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="College retrieved successfully."
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(
            data=serializer.data,
            message="Colleges retrieved successfully."
        )

    @action(detail=True, methods=['post'])
    def increment_students(self, request, pk=None):
        college = self.get_object()
        increment = request.data.get('increment', 1)

        if college.current_students + increment > college.max_students:
            return self.error_response(
                message="Cannot exceed maximum student limit",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        college.current_students += increment
        college.save()
        return self.success_response(
            data={
                'current_students': college.current_students,
                'available_seats': college.available_seats
            },
            message=f"Student count incremented by {increment}"
        )

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        college = self.get_object()
        college.is_active = False
        college.save()
        return self.success_response(
            message="College deactivated successfully."
        )

    @action(detail=False, methods=['get'])
    def with_seats(self, request):
        colleges = self.get_queryset().filter(current_students__lt=F('max_students'))
        page = self.paginate_queryset(colleges)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(colleges, many=True)
        return self.success_response(
            data=serializer.data,
            message="Colleges with available seats retrieved successfully."
        )


@csrf_exempt
@require_http_methods(["GET"])
def proxy_image_to_base64(request):
    """
    Proxy endpoint to convert images to base64
    This solves CORS issues when generating PDFs with external images

    Usage: GET /api/utils/image-to-base64/?url=<image_url>

    Returns:
        JSON response with base64 encoded image or error message
    """
    image_url = request.GET.get('url')

    if not image_url:
        logger.warning('Image proxy called without URL parameter')
        return JsonResponse({
            'success': False,
            'error': 'No URL provided',
            'message': 'Please provide a url parameter'
        }, status=400)

    try:
        logger.info(f"📷 Fetching image from: {image_url}")

        # Fetch the image from the URL
        response = requests.get(
            image_url,
            timeout=15,
            verify=True,
            headers={
                'User-Agent': 'Z1-Certificate-Generator/1.0'
            }
        )
        response.raise_for_status()

        # Get content type
        content_type = response.headers.get('Content-Type', 'image/png')
        logger.info(f"  - Content type: {content_type}")
        logger.info(f"  - Content length: {len(response.content)} bytes")

        # Convert to base64
        base64_image = base64.b64encode(response.content).decode('utf-8')
        data_url = f'data:{content_type};base64,{base64_image}'

        logger.info(f"✅ Successfully converted image to base64, size: {len(base64_image)} chars")

        return JsonResponse({
            'success': True,
            'base64': data_url,
            'content_type': content_type,
            'size': len(base64_image)
        })

    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout fetching image: {image_url}")
        return JsonResponse({
            'success': False,
            'error': 'Timeout',
            'message': 'Image fetch timed out after 15 seconds'
        }, status=504)

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error fetching image: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Fetch failed',
            'message': f'Failed to fetch image: {str(e)}'
        }, status=500)

    except Exception as e:
        logger.error(f"💥 Unexpected error converting image: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': f'Unexpected error: {str(e)}'
        }, status=500)

