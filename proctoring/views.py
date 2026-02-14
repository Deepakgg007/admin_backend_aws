"""
API Views for Video Proctoring System
======================================

REST API endpoints for:
- Starting/ending proctoring sessions
- Real-time frame analysis
- Violation reporting
- Session review and analytics
"""

import base64
import json
import numpy as np
from datetime import datetime
from io import BytesIO

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile

from .models import (
    ProctoringSession,
    ProctoringViolation,
    ProctoringSettings
)
from .serializers import (
    ProctoringSessionSerializer,
    ProctoringSessionListSerializer,
    ProctoringViolationSerializer,
    ProctoringSettingsSerializer,
    FrameAnalysisRequestSerializer,
    SessionStartSerializer,
    SessionEndSerializer,
    ViolationReviewSerializer,
)
from .video_cheating_detector import VideoCheatingDetector

# Store active detectors in memory (consider Redis for production)
_active_detectors = {}


class ProctoringSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing proctoring sessions

    list: Get all sessions (admin) or user's sessions (student)
    retrieve: Get detailed session info with violations
    create: Start a new proctoring session
    partial_update: End a session
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Check if user is admin/instructor
        if hasattr(user, 'user_type') and user.user_type in ['admin', 'instructor']:
            queryset = ProctoringSession.objects.all()
        else:
            # Students can only see their own sessions
            queryset = ProctoringSession.objects.filter(student=user)

        # Filter by task
        task_id = self.request.query_params.get('task_id')
        if task_id:
            queryset = queryset.filter(task__task_id=task_id)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by risk score threshold
        min_risk = self.request.query_params.get('min_risk')
        if min_risk:
            queryset = queryset.filter(risk_score__gte=float(min_risk))

        return queryset.order_by('-started_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ProctoringSessionListSerializer
        return ProctoringSessionSerializer

    def create(self, request, *args, **kwargs):
        """Start a new proctoring session"""
        serializer = SessionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_id = serializer.validated_data['task_id']
        reference_frame = serializer.validated_data.get('reference_frame')

        # Get the task
        from courses.models import Task
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check for existing active session
        existing = ProctoringSession.objects.filter(
            student=request.user,
            task=task,
            status='active'
        ).first()

        if existing:
            return Response(
                {'error': 'Active session already exists for this task',
                 'session_id': str(existing.session_id)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get proctoring settings
        settings = ProctoringSettings.objects.filter(task=task).first()
        if not settings:
            # Create default settings
            settings = ProctoringSettings.objects.create(task=task)

        # Create session
        session = ProctoringSession.objects.create(
            student=request.user,
            task=task,
            status='active',
            session_metadata={'settings_id': settings.id}
        )

        # Initialize detector
        detector = VideoCheatingDetector(config=settings.to_detector_config())

        # Process reference frame if provided
        if reference_frame:
            try:
                frame_data = base64.b64decode(reference_frame.split(',')[1]
                                              if ',' in reference_frame else reference_frame)
                nparr = np.frombuffer(frame_data, np.uint8)
                reference_image = decode_image(nparr)
                if reference_image is not None:
                    detector.start_session(
                        student_id=str(request.user.id),
                        quiz_id=str(task.task_id),
                        reference_frame=reference_image
                    )
                else:
                    detector.start_session(
                        student_id=str(request.user.id),
                        quiz_id=str(task.task_id)
                    )
            except Exception as e:
                detector.start_session(
                    student_id=str(request.user.id),
                    quiz_id=str(task.task_id)
                )
        else:
            detector.start_session(
                student_id=str(request.user.id),
                quiz_id=str(task.task_id)
            )

        # Store detector for this session
        _active_detectors[str(session.session_id)] = detector

        return Response({
            'session_id': str(session.session_id),
            'status': 'active',
            'message': 'Proctoring session started',
            'settings': ProctoringSettingsSerializer(settings).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        """End a proctoring session"""
        session = self.get_object()

        if session.status != 'active':
            return Response(
                {'error': 'Session is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get detector and get summary
        session_id = str(session.session_id)
        detector = _active_detectors.get(session_id)

        if detector:
            summary = detector.end_session()
            del _active_detectors[session_id]

            # Update session with summary data
            session.status = 'completed'
            session.ended_at = timezone.now()
            session.total_frames = summary.get('total_frames', 0)
            session.face_present_frames = int(
                session.total_frames * summary.get('statistics', {}).get('face_present_percentage', 100) / 100
            )
            session.face_absent_frames = int(
                session.total_frames * summary.get('statistics', {}).get('face_absent_percentage', 0) / 100
            )
            session.multiple_face_frames = int(
                session.total_frames * summary.get('statistics', {}).get('multiple_face_percentage', 0) / 100
            )
            session.look_away_frames = int(
                session.total_frames * summary.get('statistics', {}).get('look_away_percentage', 0) / 100
            )
            session.risk_score = summary.get('risk_score', 0)
            session.save()

            # Create violation records
            for v in summary.get('violations', []):
                ProctoringViolation.objects.create(
                    session=session,
                    violation_type=v['type'],
                    severity=v['severity'],
                    confidence=v['confidence'],
                    frame_number=v['frame_number'],
                    details=v['details'],
                    timestamp=datetime.fromisoformat(v['timestamp'])
                )

            # Check if session should be terminated due to violations
            if session.high_severity_count >= 3:
                session.status = 'terminated'
                session.save()

        else:
            session.status = 'completed'
            session.ended_at = timezone.now()
            session.save()

        return Response({
            'session_id': str(session.session_id),
            'status': session.status,
            'risk_score': float(session.risk_score),
            'summary': session.get_summary()
        })

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get current session status"""
        session = self.get_object()
        session_id = str(session.session_id)
        detector = _active_detectors.get(session_id)

        if detector:
            current_status = detector.get_current_status()
            return Response({
                'session': ProctoringSessionSerializer(session).data,
                'real_time_status': current_status
            })

        return Response({
            'session': ProctoringSessionSerializer(session).data,
            'real_time_status': None
        })

    @action(detail=True, methods=['get'])
    def violations(self, request, pk=None):
        """Get all violations for a session"""
        session = self.get_object()
        violations = session.violations.all()
        serializer = ProctoringViolationSerializer(violations, many=True)
        return Response(serializer.data)


class ProctoringViolationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing violations"""
    permission_classes = [IsAuthenticated]
    serializer_class = ProctoringViolationSerializer

    def get_queryset(self):
        user = self.request.user

        if hasattr(user, 'user_type') and user.user_type in ['admin', 'instructor']:
            queryset = ProctoringViolation.objects.all()
        else:
            queryset = ProctoringViolation.objects.filter(session__student=user)

        # Filters
        session_id = self.request.query_params.get('session_id')
        if session_id:
            queryset = queryset.filter(session__session_id=session_id)

        violation_type = self.request.query_params.get('type')
        if violation_type:
            queryset = queryset.filter(violation_type=violation_type)

        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        return queryset.order_by('-timestamp')

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Mark a violation as reviewed"""
        violation = self.get_object()

        # Check permission
        if not hasattr(request.user, 'user_type') or request.user.user_type not in ['admin', 'instructor']:
            return Response(
                {'error': 'Only instructors can review violations'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ViolationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        violation.reviewed = True
        violation.reviewed_by = request.user
        violation.reviewed_at = timezone.now()
        violation.is_false_positive = serializer.validated_data['is_false_positive']
        violation.review_notes = serializer.validated_data.get('review_notes', '')
        violation.save()

        return Response({
            'message': 'Violation reviewed',
            'violation': ProctoringViolationSerializer(violation).data
        })


class ProctoringSettingsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing proctoring settings"""
    permission_classes = [IsAuthenticated]
    serializer_class = ProctoringSettingsSerializer

    def get_queryset(self):
        return ProctoringSettings.objects.all()

    def perform_create(self, serializer):
        # Only admins/instructors can create settings
        if not hasattr(self.request.user, 'user_type') or \
           self.request.user.user_type not in ['admin', 'instructor']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only instructors can modify settings")
        serializer.save()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_frame(request):
    """
    Analyze a single frame for cheating detection

    Request body:
        - session_id: UUID of active session
        - frame_data: Base64 encoded frame image
        - frame_number: Current frame number

    Returns:
        - Analysis results including any violations
    """
    serializer = FrameAnalysisRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    session_id = serializer.validated_data['session_id']
    frame_number = serializer.validated_data['frame_number']
    frame_data = serializer.validated_data['frame_data']

    # Get session
    try:
        session = ProctoringSession.objects.get(session_id=session_id)
    except ProctoringSession.DoesNotExist:
        return Response(
            {'error': 'Session not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check session is active
    if session.status != 'active':
        return Response(
            {'error': 'Session is not active'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get detector
    detector = _active_detectors.get(str(session_id))
    if not detector:
        return Response(
            {'error': 'No active detector for session'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Decode frame
    try:
        # Handle data URL format
        if ',' in frame_data:
            frame_data = frame_data.split(',')[1]

        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return Response(
                {'error': 'Could not decode frame'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except Exception as e:
        return Response(
            {'error': f'Frame decode error: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Analyze frame
    result = detector.analyze_frame(frame)

    # Update session stats
    session.total_frames += 1
    if not result.get('looking_at_screen', True):
        session.look_away_frames += 1
    if result['faces_detected'] == 0:
        session.face_absent_frames += 1
    else:
        session.face_present_frames += 1
    if result['faces_detected'] > 1:
        session.multiple_face_frames += 1
    session.save(update_fields=[
        'total_frames', 'face_present_frames', 'face_absent_frames',
        'multiple_face_frames', 'look_away_frames'
    ])

    # If violation detected, store it
    if result['violation_detected']:
        # Optionally capture screenshot
        settings = ProctoringSettings.objects.filter(task=session.task).first()
        screenshot_file = None

        if settings and settings.capture_screenshots:
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            screenshot_file = ContentFile(
                buffer.tobytes(),
                name=f'violation_{session_id}_{frame_number}.jpg'
            )

        ProctoringViolation.objects.create(
            session=session,
            violation_type=result['violation_type'],
            severity=result['severity'],
            confidence=result.get('confidence', 0.5),
            frame_number=frame_number,
            details=result.get('details', {}),
            screenshot=screenshot_file
        )

        # Check for auto-terminate
        if settings and settings.auto_terminate_on_high_severity:
            if result['severity'] == 'high':
                high_count = session.violations.filter(severity='high').count()
                if high_count >= settings.auto_terminate_threshold:
                    session.status = 'terminated'
                    session.ended_at = timezone.now()
                    session.save()
                    result['session_terminated'] = True

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_assessment(request, session_id):
    """
    Get risk assessment for a session

    Returns risk score, level, and recommendation
    """
    try:
        session = ProctoringSession.objects.get(session_id=session_id)
    except ProctoringSession.DoesNotExist:
        return Response(
            {'error': 'Session not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    risk_score = float(session.risk_score)

    # Determine risk level
    if risk_score < 20:
        risk_level = 'low'
        recommendation = 'No significant concerns detected.'
    elif risk_score < 50:
        risk_level = 'medium'
        recommendation = 'Some suspicious activity detected. Review recommended.'
    elif risk_score < 75:
        risk_level = 'high'
        recommendation = 'Multiple indicators of potential academic dishonesty. Mandatory review required.'
    else:
        risk_level = 'critical'
        recommendation = 'Severe violations detected. Consider invalidating assessment.'

    return Response({
        'session_id': str(session.session_id),
        'risk_score': risk_score,
        'risk_level': risk_level,
        'recommendation': recommendation,
        'violation_breakdown': {
            'high': session.high_severity_count,
            'medium': session.medium_severity_count,
            'low': session.low_severity_count,
        },
        'statistics': {
            'face_absent_percentage': (
                session.face_absent_frames / max(1, session.total_frames) * 100
            ),
            'multiple_face_percentage': (
                session.multiple_face_frames / max(1, session.total_frames) * 100
            ),
            'look_away_percentage': (
                session.look_away_frames / max(1, session.total_frames) * 100
            ),
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def proctoring_dashboard(request):
    """
    Dashboard data for proctoring overview

    Returns statistics and recent sessions with high risk
    """
    user = request.user

    # Check permissions
    if not hasattr(user, 'user_type') or user.user_type not in ['admin', 'instructor']:
        return Response(
            {'error': 'Instructor access required'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get statistics
    total_sessions = ProctoringSession.objects.count()
    active_sessions = ProctoringSession.objects.filter(status='active').count()

    # High risk sessions (unreviewed)
    high_risk_sessions = ProctoringSession.objects.filter(
        risk_score__gte=50,
        status='completed'
    ).exclude(
        violations__reviewed=True
    ).distinct().count()

    # Recent violations
    recent_violations = ProctoringViolation.objects.filter(
        reviewed=False,
        severity='high'
    ).order_by('-timestamp')[:10]

    # Sessions needing review
    sessions_needing_review = ProctoringSession.objects.filter(
        risk_score__gte=30,
        status='completed'
    ).exclude(
        violations__reviewed=True
    ).distinct().order_by('-risk_score')[:20]

    return Response({
        'statistics': {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'high_risk_sessions': high_risk_sessions,
            'unreviewed_violations': recent_violations.count(),
        },
        'recent_high_severity_violations': ProctoringViolationSerializer(
            recent_violations, many=True
        ).data,
        'sessions_needing_review': ProctoringSessionListSerializer(
            sessions_needing_review, many=True
        ).data,
    })


# Import cv2 for frame decoding
import cv2


def decode_image(nparr):
    """Decode numpy array to image"""
    try:
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        return None
