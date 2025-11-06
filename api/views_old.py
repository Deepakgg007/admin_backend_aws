from rest_framework import generics, status, viewsets, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import University, Organization, College
from .serializers import (
    UserRegistrationSerializer, UserSerializer, UserProfileUpdateSerializer,
    LoginSerializer, LoginResponseSerializer, ChangePasswordSerializer,
    UniversitySerializer, OrganizationSerializer,
    CollegeSerializer, CollegeListSerializer
)
from .permissions import IsOwnerOrReadOnly
from .utils import StandardResponseMixin, CustomPagination

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView, StandardResponseMixin):
    @extend_schema(
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: OpenApiResponse(description='Invalid credentials')
        },
        summary="User Login",
        description="Login with email and password to get JWT tokens and user information including staff/superuser status"
    )
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        # Create response data
        response_data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }

        return self.success_response(
            data=response_data,
            message="Login successful."
        )


class UserRegistrationView(generics.CreateAPIView, StandardResponseMixin):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return self.success_response(
            data={
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            message="Registration successful.",
            status_code=status.HTTP_201_CREATED
        )


class UserProfileView(generics.RetrieveUpdateAPIView, StandardResponseMixin):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Profile retrieved successfully."
        )

    def update(self, request, *args, **kwargs):
        serializer = UserProfileUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            data=UserSerializer(request.user).data,
            message="Profile updated successfully."
        )


class ChangePasswordView(generics.UpdateAPIView, StandardResponseMixin):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            message="Password changed successfully."
        )






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
                'auth': {
                    'register': '/api/auth/register/',
                    'login': '/api/auth/login/',
                    'refresh': '/api/auth/refresh/',
                    'profile': '/api/auth/profile/',
                    'change-password': '/api/auth/change-password/',
                },
                'docs': {
                    'swagger': '/api/docs/',
                    'redoc': '/api/redoc/',
                },
                'universities': '/api/universities/',
                'organizations': '/api/organizations/',
                'colleges': '/api/colleges/',
                }
            },
            message="Welcome to Z1 Solution API"
        )

api_root = APIRootView.as_view()


class UniversityViewSet(viewsets.ModelViewSet):
    queryset = University.objects.all()  # Show all universities
    serializer_class = UniversitySerializer
    permission_classes = [IsAuthenticated]  # Requires authentication
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def organizations(self, request, pk=None):
        university = self.get_object()
        organizations = university.organizations.filter(is_active=True)
        serializer = OrganizationSerializer(organizations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def colleges(self, request, pk=None):
        university = self.get_object()
        colleges = College.objects.filter(
            organization__university=university,
            is_active=True
        )
        serializer = CollegeListSerializer(colleges, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        university = self.get_object()
        university.is_active = False
        university.save()
        return Response({'message': 'University deactivated successfully'})


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()  # Show all organizations
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'university__name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()
        university_id = self.request.query_params.get('university')
        if university_id:
            queryset = queryset.filter(university_id=university_id)
        return queryset.select_related('university', 'created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def colleges(self, request, pk=None):
        organization = self.get_object()
        colleges = organization.colleges.filter(is_active=True)
        serializer = CollegeListSerializer(colleges, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        organization = self.get_object()
        organization.is_active = False
        organization.save()
        return Response({'message': 'Organization deactivated successfully'})


class CollegeViewSet(viewsets.ModelViewSet):
    queryset = College.objects.all()  # Show all colleges
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'organization__name', 'organization__university__name']
    ordering_fields = ['name', 'created_at', 'max_students']
    ordering = ['name']

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
            queryset = queryset.filter(current_students__lt=models.F('max_students'))

        return queryset.select_related('organization__university', 'created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def increment_students(self, request, pk=None):
        college = self.get_object()
        increment = request.data.get('increment', 1)

        if college.current_students + increment > college.max_students:
            return Response(
                {'error': 'Cannot exceed maximum student limit'},
                status=status.HTTP_400_BAD_REQUEST
            )

        college.current_students += increment
        college.save()
        return Response({
            'message': f'Student count incremented by {increment}',
            'current_students': college.current_students,
            'available_seats': college.available_seats
        })

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        college = self.get_object()
        college.is_active = False
        college.save()
        return Response({'message': 'College deactivated successfully'})

    @action(detail=False, methods=['get'])
    def with_seats(self, request):
        colleges = self.get_queryset().filter(current_students__lt=models.F('max_students'))
        serializer = self.get_serializer(colleges, many=True)
        return Response(serializer.data)


# Import models.F for the queryset filters
from django.db import models
