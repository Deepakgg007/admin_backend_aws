from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChallengeViewSet, StarterCodeViewSet, TestCaseViewSet
)

router = DefaultRouter()
router.register('challenges', ChallengeViewSet, basename='challenge')
router.register('starter-codes', StarterCodeViewSet, basename='starter-code')
router.register('test-cases', TestCaseViewSet, basename='test-case')

urlpatterns = [
    path('', include(router.urls)),
]
