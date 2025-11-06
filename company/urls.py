# company/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CompanyViewSet, ConceptViewSet, ConceptChallengeViewSet,
     JobViewSet
)

router = DefaultRouter()
router.register('companies', CompanyViewSet, basename='company')
router.register('concepts', ConceptViewSet, basename='concept')
router.register('concept-challenges', ConceptChallengeViewSet, basename='concept-challenge')

router.register('jobs', JobViewSet, basename='job')

urlpatterns = [
    path('', include(router.urls)),
]
