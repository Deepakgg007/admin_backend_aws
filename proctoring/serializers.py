"""
Serializers for Proctoring API
"""

from rest_framework import serializers
from .models import ProctoringSession, ProctoringViolation, ProctoringSettings


class ProctoringViolationSerializer(serializers.ModelSerializer):
    """Serializer for violation events"""

    violation_type_display = serializers.CharField(
        source='get_violation_type_display',
        read_only=True
    )
    severity_display = serializers.CharField(
        source='get_severity_display',
        read_only=True
    )

    class Meta:
        model = ProctoringViolation
        fields = [
            'violation_id',
            'violation_type',
            'violation_type_display',
            'severity',
            'severity_display',
            'confidence',
            'timestamp',
            'frame_number',
            'details',
            'screenshot',
            'reviewed',
            'reviewed_by',
            'reviewed_at',
            'review_notes',
            'is_false_positive',
        ]
        read_only_fields = [
            'violation_id',
            'timestamp',
            'reviewed_by',
            'reviewed_at',
        ]


class ProctoringSessionSerializer(serializers.ModelSerializer):
    """Serializer for proctoring sessions"""

    violations = ProctoringViolationSerializer(many=True, read_only=True)
    student_email = serializers.EmailField(source='student.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)
    duration_seconds = serializers.ReadOnlyField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ProctoringSession
        fields = [
            'session_id',
            'student',
            'student_email',
            'task',
            'task_title',
            'status',
            'started_at',
            'ended_at',
            'duration_seconds',
            'total_frames',
            'face_present_frames',
            'face_absent_frames',
            'multiple_face_frames',
            'look_away_frames',
            'risk_score',
            'violation_count',
            'high_severity_count',
            'medium_severity_count',
            'low_severity_count',
            'violations',
            'summary',
            'session_metadata',
        ]
        read_only_fields = [
            'session_id',
            'started_at',
            'ended_at',
            'risk_score',
        ]

    def get_summary(self, obj):
        return obj.get_summary()


class ProctoringSessionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing sessions"""

    student_email = serializers.EmailField(source='student.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)
    duration_seconds = serializers.ReadOnlyField()

    class Meta:
        model = ProctoringSession
        fields = [
            'session_id',
            'student_email',
            'task_title',
            'status',
            'started_at',
            'ended_at',
            'duration_seconds',
            'violation_count',
            'risk_score',
        ]


class ProctoringSettingsSerializer(serializers.ModelSerializer):
    """Serializer for proctoring settings"""

    class Meta:
        model = ProctoringSettings
        fields = [
            'id',
            'task',
            'college',
            'face_detection_enabled',
            'gaze_detection_enabled',
            'object_detection_enabled',
            'face_verification_enabled',
            'max_absent_frames',
            'max_multiple_face_frames',
            'max_look_away_frames',
            'min_face_confidence',
            'min_object_confidence',
            'face_similarity_threshold',
            'auto_terminate_on_high_severity',
            'auto_terminate_threshold',
            'capture_screenshots',
            'capture_interval_frames',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FrameAnalysisRequestSerializer(serializers.Serializer):
    """Serializer for frame analysis requests from client"""

    session_id = serializers.UUIDField()
    frame_data = serializers.CharField(
        help_text="Base64 encoded frame image"
    )
    frame_number = serializers.IntegerField(min_value=0)
    timestamp = serializers.FloatField(
        help_text="Client-side timestamp in seconds"
    )


class FrameAnalysisResponseSerializer(serializers.Serializer):
    """Serializer for frame analysis response"""

    frame_number = serializers.IntegerField()
    timestamp = serializers.CharField()
    violation_detected = serializers.BooleanField()
    violation_type = serializers.CharField(allow_null=True)
    severity = serializers.CharField()
    faces_detected = serializers.IntegerField()
    looking_at_screen = serializers.BooleanField()
    suspicious_objects = serializers.ListField()
    confidence = serializers.FloatField()
    details = serializers.DictField()


class SessionStartSerializer(serializers.Serializer):
    """Serializer for starting a new proctoring session"""

    task_id = serializers.UUIDField()
    reference_frame = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Base64 encoded reference face image"
    )


class SessionEndSerializer(serializers.Serializer):
    """Serializer for ending a proctoring session"""

    session_id = serializers.UUIDField()


class ViolationReviewSerializer(serializers.Serializer):
    """Serializer for reviewing a violation"""

    is_false_positive = serializers.BooleanField()
    review_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )


class RiskScoreSerializer(serializers.Serializer):
    """Serializer for risk score response"""

    session_id = serializers.UUIDField()
    risk_score = serializers.FloatField()
    risk_level = serializers.CharField()
    recommendation = serializers.CharField()
