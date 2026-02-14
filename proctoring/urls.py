"""
URL Routes for Proctoring API
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'sessions', views.ProctoringSessionViewSet, basename='proctoring-session')
router.register(r'violations', views.ProctoringViolationViewSet, basename='proctoring-violation')
router.register(r'settings', views.ProctoringSettingsViewSet, basename='proctoring-settings')

urlpatterns = [
    path('', include(router.urls)),

    # Frame analysis endpoint
    path('analyze-frame/', views.analyze_frame, name='proctoring-analyze-frame'),

    # Risk assessment
    path('risk-assessment/<uuid:session_id>/',
         views.get_risk_assessment, name='proctoring-risk-assessment'),

    # Dashboard
    path('dashboard/', views.proctoring_dashboard, name='proctoring-dashboard'),
]
