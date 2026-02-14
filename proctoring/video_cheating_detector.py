"""
Video-Based Cheating Detection System for Online Quizzes
=========================================================

This module provides real-time video analysis to detect potential cheating
behaviors during online assessments.

Features:
- Face presence detection
- Multiple face detection
- Gaze/look-away detection
- Object detection (phones, books)
- Face verification (same person)
- Suspicious behavior logging

Dependencies:
    pip install opencv-python mediapipe numpy torch torchvision

Usage:
    detector = VideoCheatingDetector()
    detector.start_session(student_id="123", quiz_id="quiz_1")

    # In video frame loop:
    result = detector.analyze_frame(frame)
    if result['violation_detected']:
        print(f"Violation: {result['violation_type']}")

    detector.end_session()
"""

import cv2
import numpy as np
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("MediaPipe not installed. Face mesh features disabled.")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not installed. Advanced detection features disabled.")


@dataclass
class ViolationEvent:
    """Represents a single violation event"""
    timestamp: datetime
    violation_type: str
    severity: str  # 'low', 'medium', 'high'
    confidence: float
    details: Dict
    frame_number: int = 0


@dataclass
class ProctoringSession:
    """Tracks the state of a proctoring session"""
    student_id: str
    quiz_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_frames: int = 0
    violations: List[ViolationEvent] = field(default_factory=list)
    reference_face_encoding: Optional[np.ndarray] = None
    face_present_frames: int = 0
    face_absent_frames: int = 0
    multiple_face_frames: int = 0
    look_away_frames: int = 0


class FaceDetector:
    """Face detection using MediaPipe or OpenCV fallback"""

    def __init__(self, min_detection_confidence: float = 0.5):
        self.min_detection_confidence = min_detection_confidence

        if MEDIAPIPE_AVAILABLE:
            self.mp_face_detection = mp.solutions.face_detection
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_detection = self.mp_face_detection.FaceDetection(
                min_detection_confidence=min_detection_confidence
            )
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self.use_mediapipe = True
        else:
            # Fallback to OpenCV Haar Cascade
            self.haar_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            self.use_mediapipe = False

    def detect_faces(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect faces in frame and return list of face info

        Returns:
            List of dicts with keys: 'bbox', 'confidence', 'landmarks'
        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = []

        if self.use_mediapipe:
            results = self.face_detection.process(rgb_frame)
            if results.detections:
                for detection in results.detections:
                    bboxC = detection.location_data.relative_bounding_box
                    h, w, _ = frame.shape
                    bbox = {
                        'x': int(bboxC.xmin * w),
                        'y': int(bboxC.ymin * h),
                        'width': int(bboxC.width * w),
                        'height': int(bboxC.height * h)
                    }
                    faces.append({
                        'bbox': bbox,
                        'confidence': detection.score[0] if detection.score else 0.0,
                        'landmarks': None
                    })
        else:
            # OpenCV fallback
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = self.haar_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            for (x, y, w, h) in detections:
                faces.append({
                    'bbox': {'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)},
                    'confidence': 0.8,  # Haar doesn't give confidence
                    'landmarks': None
                })

        return faces

    def get_face_landmarks(self, frame: np.ndarray) -> Optional[List]:
        """Get facial landmarks for gaze detection"""
        if not self.use_mediapipe:
            return None

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        if results.multi_face_landmarks:
            # Return first face's landmarks
            return results.multi_face_landmarks[0]
        return None


class GazeDetector:
    """Detects if user is looking away from screen"""

    def __init__(self):
        # Iris landmark indices in MediaPipe face mesh
        self.LEFT_IRIS = [468, 469, 470, 471, 472]
        self.RIGHT_IRIS = [473, 474, 475, 476, 477]

        # Eye corners for reference
        self.LEFT_EYE_CORNERS = [33, 133]
        self.RIGHT_EYE_CORNERS = [362, 263]

    def estimate_gaze(self, landmarks, frame_width: int, frame_height: int) -> Dict:
        """
        Estimate gaze direction from landmarks

        Returns:
            Dict with 'looking_at_screen', 'gaze_direction', 'confidence'
        """
        if landmarks is None:
            return {'looking_at_screen': True, 'gaze_direction': 'unknown', 'confidence': 0.0}

        try:
            # Get iris centers
            left_iris_x = sum(landmarks.landmark[i].x for i in self.LEFT_IRIS[:4]) / 4
            right_iris_x = sum(landmarks.landmark[i].x for i in self.RIGHT_IRIS[:4]) / 4

            # Get eye corner positions
            left_eye_inner = landmarks.landmark[self.LEFT_EYE_CORNERS[0]].x
            left_eye_outer = landmarks.landmark[self.LEFT_EYE_CORNERS[1]].x
            right_eye_inner = landmarks.landmark[self.RIGHT_EYE_CORNERS[0]].x
            right_eye_outer = landmarks.landmark[self.RIGHT_EYE_CORNERS[1]].x

            # Calculate horizontal gaze ratio
            left_eye_width = left_eye_outer - left_eye_inner
            right_eye_width = right_eye_outer - right_eye_inner

            left_gaze_ratio = (left_iris_x - left_eye_inner) / left_eye_width if left_eye_width > 0 else 0.5
            right_gaze_ratio = (right_iris_x - right_eye_inner) / right_eye_width if right_eye_width > 0 else 0.5

            avg_gaze_ratio = (left_gaze_ratio + right_gaze_ratio) / 2

            # Determine gaze direction
            if avg_gaze_ratio < 0.35:
                direction = 'left'
                looking_at_screen = False
            elif avg_gaze_ratio > 0.65:
                direction = 'right'
                looking_at_screen = False
            else:
                direction = 'center'
                looking_at_screen = True

            return {
                'looking_at_screen': looking_at_screen,
                'gaze_direction': direction,
                'confidence': 0.7,
                'gaze_ratio': avg_gaze_ratio
            }
        except Exception as e:
            logger.debug(f"Gaze estimation error: {e}")
            return {'looking_at_screen': True, 'gaze_direction': 'unknown', 'confidence': 0.0}


class ObjectDetector:
    """Detects suspicious objects like phones, books"""

    def __init__(self):
        self.suspicious_objects = ['cell phone', 'mobile phone', 'book', 'laptop', 'tablet']

        # Try to load YOLO or use simple detection
        self.detector = None
        if TORCH_AVAILABLE:
            self._load_yolo()

    def _load_yolo(self):
        """Load YOLO model for object detection"""
        try:
            # Load YOLOv5 from torch hub (requires internet first time)
            self.detector = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
            self.detector.eval()
        except Exception as e:
            logger.warning(f"Could not load YOLO model: {e}")
            self.detector = None

    def detect_suspicious_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect suspicious objects in frame

        Returns:
            List of detected suspicious objects with confidence
        """
        if self.detector is None:
            return []

        try:
            results = self.detector(frame)
            detections = []

            for *box, conf, cls in results.xyxy[0]:
                label = results.names[int(cls)]
                if any(obj in label.lower() for obj in self.suspicious_objects):
                    detections.append({
                        'label': label,
                        'confidence': float(conf),
                        'bbox': [int(x) for x in box]
                    })

            return detections
        except Exception as e:
            logger.debug(f"Object detection error: {e}")
            return []


class VideoCheatingDetector:
    """
    Main class for video-based cheating detection

    Integrates multiple detection modules:
    - Face detection (presence, count)
    - Gaze tracking
    - Object detection
    - Face verification
    """

    # Configuration
    DEFAULT_CONFIG = {
        'face_detection': {
            'enabled': True,
            'min_confidence': 0.5,
            'max_absent_frames': 30,  # ~1 sec at 30fps
            'max_multiple_face_frames': 15,  # ~0.5 sec
        },
        'gaze_detection': {
            'enabled': True,
            'max_look_away_frames': 60,  # ~2 sec
            'min_consecutive_frames': 5,
        },
        'object_detection': {
            'enabled': True,
            'min_confidence': 0.5,
        },
        'face_verification': {
            'enabled': False,  # Requires face_recognition library
            'similarity_threshold': 0.6,
        },
        'alert_thresholds': {
            'face_absent_violation': 30,
            'multiple_face_violation': 15,
            'look_away_violation': 60,
        }
    }

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the cheating detector

        Args:
            config: Optional configuration dict to override defaults
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.session: Optional[ProctoringSession] = None
        self.frame_number = 0

        # Initialize detectors
        self.face_detector = FaceDetector(
            min_detection_confidence=self.config['face_detection']['min_confidence']
        )
        self.gaze_detector = GazeDetector()
        self.object_detector = ObjectDetector()

        # Tracking state
        self.consecutive_absent_frames = 0
        self.consecutive_multiple_faces = 0
        self.consecutive_look_away = 0
        self.look_away_history = deque(maxlen=30)  # Track last 30 frames

    def start_session(self, student_id: str, quiz_id: str,
                      reference_frame: Optional[np.ndarray] = None) -> None:
        """
        Start a new proctoring session

        Args:
            student_id: Unique student identifier
            quiz_id: Unique quiz/assessment identifier
            reference_frame: Optional reference frame for face verification
        """
        self.session = ProctoringSession(
            student_id=student_id,
            quiz_id=quiz_id,
            start_time=datetime.now()
        )
        self.frame_number = 0
        self.consecutive_absent_frames = 0
        self.consecutive_multiple_faces = 0
        self.consecutive_look_away = 0
        self.look_away_history.clear()

        # Store reference face if provided
        if reference_frame is not None:
            faces = self.face_detector.detect_faces(reference_frame)
            if len(faces) == 1:
                self.session.reference_face_encoding = self._extract_face_encoding(
                    reference_frame, faces[0]
                )

        logger.info(f"Started proctoring session for student {student_id}, quiz {quiz_id}")

    def _extract_face_encoding(self, frame: np.ndarray, face_info: Dict) -> np.ndarray:
        """Extract face encoding for verification"""
        bbox = face_info['bbox']
        face_roi = frame[
            max(0, bbox['y']):min(frame.shape[0], bbox['y'] + bbox['height']),
            max(0, bbox['x']):min(frame.shape[1], bbox['x'] + bbox['width'])
        ]
        # Simple encoding using histogram
        try:
            face_resized = cv2.resize(face_roi, (64, 64))
            gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)
            return gray.flatten().astype(np.float32) / 255.0
        except Exception:
            return np.zeros(4096, dtype=np.float32)

    def analyze_frame(self, frame: np.ndarray) -> Dict:
        """
        Analyze a single frame for cheating indicators

        Args:
            frame: BGR image from webcam/video

        Returns:
            Dict with analysis results including any violations
        """
        if self.session is None:
            raise RuntimeError("No active session. Call start_session() first.")

        self.frame_number += 1
        self.session.total_frames += 1

        result = {
            'frame_number': self.frame_number,
            'timestamp': datetime.now().isoformat(),
            'violation_detected': False,
            'violation_type': None,
            'severity': 'none',
            'faces_detected': 0,
            'looking_at_screen': True,
            'suspicious_objects': [],
            'confidence': 1.0,
            'details': {}
        }

        # 1. Face Detection
        if self.config['face_detection']['enabled']:
            faces = self.face_detector.detect_faces(frame)
            result['faces_detected'] = len(faces)
            result['face_confidence'] = max((f['confidence'] for f in faces), default=0.0)

            # Check for face presence
            if len(faces) == 0:
                self.session.face_absent_frames += 1
                self.consecutive_absent_frames += 1
                self.consecutive_multiple_faces = 0

                if self.consecutive_absent_frames >= self.config['alert_thresholds']['face_absent_violation']:
                    self._record_violation(
                        'face_not_detected',
                        'medium',
                        confidence=0.9,
                        details={'consecutive_frames': self.consecutive_absent_frames}
                    )
                    result['violation_detected'] = True
                    result['violation_type'] = 'face_not_detected'
                    result['severity'] = 'medium'
            else:
                self.session.face_present_frames += 1
                self.consecutive_absent_frames = 0
                result['details']['face_bbox'] = faces[0]['bbox']

            # Check for multiple faces
            if len(faces) > 1:
                self.session.multiple_face_frames += 1
                self.consecutive_multiple_faces += 1

                if self.consecutive_multiple_faces >= self.config['alert_thresholds']['multiple_face_violation']:
                    self._record_violation(
                        'multiple_faces_detected',
                        'high',
                        confidence=0.85,
                        details={'face_count': len(faces)}
                    )
                    result['violation_detected'] = True
                    result['violation_type'] = 'multiple_faces_detected'
                    result['severity'] = 'high'
            else:
                self.consecutive_multiple_faces = 0

            # 2. Gaze Detection (only if face detected)
            if self.config['gaze_detection']['enabled'] and len(faces) > 0:
                landmarks = self.face_detector.get_face_landmarks(frame)
                gaze_result = self.gaze_detector.estimate_gaze(
                    landmarks, frame.shape[1], frame.shape[0]
                )

                result['looking_at_screen'] = gaze_result['looking_at_screen']
                result['gaze_direction'] = gaze_result.get('gaze_direction', 'unknown')
                result['details']['gaze_ratio'] = gaze_result.get('gaze_ratio', 0.5)

                self.look_away_history.append(not gaze_result['looking_at_screen'])

                if not gaze_result['looking_at_screen']:
                    self.session.look_away_frames += 1
                    self.consecutive_look_away += 1

                    # Check for prolonged look-away
                    if self.consecutive_look_away >= self.config['alert_thresholds']['look_away_violation']:
                        self._record_violation(
                            'prolonged_look_away',
                            'low',
                            confidence=gaze_result['confidence'],
                            details={
                                'consecutive_frames': self.consecutive_look_away,
                                'gaze_direction': gaze_result['gaze_direction']
                            }
                        )
                        result['violation_detected'] = True
                        result['violation_type'] = 'prolonged_look_away'
                        result['severity'] = 'low'
                else:
                    self.consecutive_look_away = 0

                # Check for suspicious look-away pattern
                if len(self.look_away_history) == 30:
                    look_away_ratio = sum(self.look_away_history) / 30
                    if look_away_ratio > 0.5:  # Looking away more than 50% of time
                        self._record_violation(
                            'suspicious_gaze_pattern',
                            'medium',
                            confidence=0.7,
                            details={'look_away_ratio': look_away_ratio}
                        )
                        result['violation_detected'] = True
                        result['violation_type'] = 'suspicious_gaze_pattern'
                        result['severity'] = 'medium'

        # 3. Object Detection
        if self.config['object_detection']['enabled']:
            objects = self.object_detector.detect_suspicious_objects(frame)
            if objects:
                result['suspicious_objects'] = objects
                self._record_violation(
                    'suspicious_object_detected',
                    'high',
                    confidence=max(o['confidence'] for o in objects),
                    details={'objects': objects}
                )
                result['violation_detected'] = True
                result['violation_type'] = 'suspicious_object_detected'
                result['severity'] = 'high'

        # 4. Face Verification (if reference available)
        if (self.config['face_verification']['enabled'] and
            self.session.reference_face_encoding is not None and
            len(faces) > 0):
            current_encoding = self._extract_face_encoding(frame, faces[0])
            similarity = self._compare_faces(
                self.session.reference_face_encoding,
                current_encoding
            )
            result['details']['face_similarity'] = similarity

            if similarity < self.config['face_verification']['similarity_threshold']:
                self._record_violation(
                    'face_mismatch',
                    'high',
                    confidence=1 - similarity,
                    details={'similarity_score': similarity}
                )
                result['violation_detected'] = True
                result['violation_type'] = 'face_mismatch'
                result['severity'] = 'high'

        return result

    def _compare_faces(self, encoding1: np.ndarray, encoding2: np.ndarray) -> float:
        """Compare two face encodings and return similarity score"""
        if encoding1 is None or encoding2 is None:
            return 0.0
        try:
            # Cosine similarity
            dot_product = np.dot(encoding1, encoding2)
            norm1 = np.linalg.norm(encoding1)
            norm2 = np.linalg.norm(encoding2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
        except Exception:
            return 0.0

    def _record_violation(self, violation_type: str, severity: str,
                         confidence: float, details: Dict) -> None:
        """Record a violation event"""
        violation = ViolationEvent(
            timestamp=datetime.now(),
            violation_type=violation_type,
            severity=severity,
            confidence=confidence,
            details=details,
            frame_number=self.frame_number
        )
        self.session.violations.append(violation)
        logger.warning(
            f"VIOLATION: {violation_type} (severity: {severity}, "
            f"confidence: {confidence:.2f}, frame: {self.frame_number})"
        )

    def end_session(self) -> Dict:
        """
        End the proctoring session and return summary

        Returns:
            Dict with session summary and all violations
        """
        if self.session is None:
            return {'error': 'No active session'}

        self.session.end_time = datetime.now()
        duration = (self.session.end_time - self.session.start_time).total_seconds()

        summary = {
            'student_id': self.session.student_id,
            'quiz_id': self.session.quiz_id,
            'start_time': self.session.start_time.isoformat(),
            'end_time': self.session.end_time.isoformat(),
            'duration_seconds': duration,
            'total_frames': self.session.total_frames,
            'statistics': {
                'face_present_percentage': (
                    self.session.face_present_frames / max(1, self.session.total_frames) * 100
                ),
                'face_absent_percentage': (
                    self.session.face_absent_frames / max(1, self.session.total_frames) * 100
                ),
                'multiple_face_percentage': (
                    self.session.multiple_face_frames / max(1, self.session.total_frames) * 100
                ),
                'look_away_percentage': (
                    self.session.look_away_frames / max(1, self.session.total_frames) * 100
                ),
            },
            'violations': [
                {
                    'timestamp': v.timestamp.isoformat(),
                    'type': v.violation_type,
                    'severity': v.severity,
                    'confidence': v.confidence,
                    'details': v.details,
                    'frame_number': v.frame_number
                }
                for v in self.session.violations
            ],
            'violation_summary': {
                'total_violations': len(self.session.violations),
                'high_severity': sum(1 for v in self.session.violations if v.severity == 'high'),
                'medium_severity': sum(1 for v in self.session.violations if v.severity == 'medium'),
                'low_severity': sum(1 for v in self.session.violations if v.severity == 'low'),
            },
            'risk_score': self._calculate_risk_score()
        }

        session = self.session
        self.session = None
        logger.info(f"Ended proctoring session. Total violations: {len(session.violations)}")

        return summary

    def _calculate_risk_score(self) -> float:
        """
        Calculate overall risk score (0-100)

        Higher score = higher probability of cheating
        """
        if self.session is None:
            return 0.0

        score = 0.0

        # Weight violations by severity
        for violation in self.session.violations:
            if violation.severity == 'high':
                score += 20
            elif violation.severity == 'medium':
                score += 10
            else:
                score += 5

        # Factor in face absence
        if self.session.total_frames > 0:
            absent_ratio = self.session.face_absent_frames / self.session.total_frames
            score += absent_ratio * 30  # Up to 30 points for face absence

            # Factor in multiple faces
            multi_face_ratio = self.session.multiple_face_frames / self.session.total_frames
            score += multi_face_ratio * 40  # Up to 40 points for multiple faces

            # Factor in look away
            look_away_ratio = self.session.look_away_frames / self.session.total_frames
            score += look_away_ratio * 20  # Up to 20 points for looking away

        return min(100.0, score)

    def get_current_status(self) -> Dict:
        """Get current session status without ending it"""
        if self.session is None:
            return {'active': False}

        return {
            'active': True,
            'student_id': self.session.student_id,
            'quiz_id': self.session.quiz_id,
            'duration_seconds': (datetime.now() - self.session.start_time).total_seconds(),
            'total_frames': self.session.total_frames,
            'total_violations': len(self.session.violations),
            'risk_score': self._calculate_risk_score(),
            'current_state': {
                'face_detected': self.consecutive_absent_frames == 0,
                'multiple_faces': self.consecutive_multiple_faces > 0,
                'looking_away': self.consecutive_look_away > 0
            }
        }


# Convenience function for quick analysis
def analyze_video_stream(source=0, student_id: str = "test",
                         quiz_id: str = "test", duration: int = 60) -> Dict:
    """
    Analyze video stream for cheating detection

    Args:
        source: Video source (0 for webcam, or path to video file)
        student_id: Student identifier
        quiz_id: Quiz identifier
        duration: Duration in seconds to analyze (0 for infinite)

    Returns:
        Session summary with violations
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return {'error': 'Could not open video source'}

    detector = VideoCheatingDetector()
    detector.start_session(student_id, quiz_id)

    start_time = time.time()
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            result = detector.analyze_frame(frame)
            frame_count += 1

            # Draw debugging info on frame
            if result['violation_detected']:
                cv2.putText(frame, f"VIOLATION: {result['violation_type']}",
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Show frame (optional - comment out for headless operation)
            cv2.imshow('Proctoring', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # Check duration
            if duration > 0 and (time.time() - start_time) >= duration:
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()

    return detector.end_session()


if __name__ == '__main__':
    # Demo usage
    print("Video Cheating Detection Demo")
    print("=" * 50)
    print("Press 'q' to quit")

    result = analyze_video_stream(source=0, student_id="demo_student", quiz_id="demo_quiz")

    print("\nSession Summary:")
    print(json.dumps(result, indent=2, default=str))
