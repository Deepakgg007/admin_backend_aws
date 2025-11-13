from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)
from .views import (
    api_root,
    UniversityViewSet, OrganizationViewSet, CollegeViewSet
)

router = DefaultRouter()
router.register('universities', UniversityViewSet, basename='university')
router.register('organizations', OrganizationViewSet, basename='organization')
router.register('colleges', CollegeViewSet, basename='college')

urlpatterns = [
    path('', api_root, name='api-root'),

    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Core API routes
    path('', include(router.urls)),

    # Include app-specific URLs
    path('', include('courses.urls')),
    path('', include('coding.urls')),
    path('', include('company.urls')),
    path('', include('course_cert.urls')),
]

