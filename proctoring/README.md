# Video Proctoring System for Quiz Cheating Detection

A comprehensive video-based proctoring system to detect cheating during online assessments.

## Features

### Detection Capabilities

| Feature | Description | Severity |
|---------|-------------|----------|
| **Face Detection** | Detects if student is present at camera | Medium |
| **Multiple Faces** | Detects if additional people are in frame | High |
| **Gaze Tracking** | Detects prolonged looking away from screen | Low |
| **Suspicious Gaze Pattern** | Detects erratic eye movements | Medium |
| **Object Detection** | Detects phones, books, laptops | High |
| **Face Verification** | Verifies same person throughout session | High |

### API Endpoints

```
POST   /api/proctoring/sessions/              # Start session
POST   /api/proctoring/sessions/{id}/end/     # End session
GET    /api/proctoring/sessions/{id}/status/  # Get status
GET    /api/proctoring/sessions/{id}/violations/  # Get violations
POST   /api/proctoring/analyze-frame/         # Analyze frame
GET    /api/proctoring/risk-assessment/{id}/  # Get risk score
GET    /api/proctoring/dashboard/             # Admin dashboard
```

## Installation

### 1. Install Python Dependencies

```bash
pip install opencv-python mediapipe numpy torch torchvision
```

### 2. Add to Django Settings

```python
# settings.py

INSTALLED_APPS = [
    # ... existing apps ...
    'proctoring',
]

# Optional: Configure media storage for evidence
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

### 3. Run Migrations

```bash
python manage.py makemigrations proctoring
python manage.py migrate
```

### 4. Add URLs

```python
# urls.py

urlpatterns = [
    # ... existing patterns ...
    path('api/proctoring/', include('proctoring.urls')),
]
```

## Usage

### Backend (Python)

```python
from proctoring.video_cheating_detector import VideoCheatingDetector

# Initialize detector
detector = VideoCheatingDetector(config={
    'face_detection': {'enabled': True},
    'gaze_detection': {'enabled': True},
})

# Start session
detector.start_session(student_id="123", quiz_id="quiz_1")

# In your video processing loop:
for frame in video_stream:
    result = detector.analyze_frame(frame)

    if result['violation_detected']:
        print(f"VIOLATION: {result['violation_type']}")
        print(f"Severity: {result['severity']}")

# End session and get summary
summary = detector.end_session()
print(f"Risk Score: {summary['risk_score']}")
```

### Frontend (JavaScript)

```javascript
// Initialize proctoring client
const proctor = new VideoProctoringClient({
    apiBaseUrl: '/api/proctoring',
    taskId: 'your-quiz-uuid',
    frameInterval: 1000, // 1 frame per second

    onViolation: (violation) => {
        alert(`Warning: ${violation.type}`);
    },

    onError: (error) => {
        console.error('Proctoring error:', error);
    }
});

// Start when quiz begins
await proctor.startSession();

// End when quiz submits
const summary = await proctor.endSession();
console.log('Risk Score:', summary.risk_score);
```

### React Integration

```jsx
import { useVideoProctoring } from './proctoring-client';

function QuizComponent({ taskId }) {
    const { status, violation, startSession, endSession } = useVideoProctoring({
        taskId,
        autoStart: true,
    });

    if (violation) {
        return (
            <div className="warning">
                <h3>Warning Detected</h3>
                <p>{violation.type}</p>
                <button onClick={() => clearViolation()}>Continue</button>
            </div>
        );
    }

    return (
        <div>
            <p>Proctoring Status: {status}</p>
            {/* Quiz content */}
        </div>
    );
}
```

## Configuration Options

### Detection Settings

```python
from proctoring.models import ProctoringSettings

settings = ProctoringSettings.objects.create(
    task=my_task,

    # Enable/disable features
    face_detection_enabled=True,
    gaze_detection_enabled=True,
    object_detection_enabled=False,  # Requires more resources

    # Thresholds (in frames)
    max_absent_frames=30,           # ~1 second at 30fps
    max_multiple_face_frames=15,    # ~0.5 seconds
    max_look_away_frames=60,        # ~2 seconds

    # Confidence thresholds
    min_face_confidence=0.5,
    min_object_confidence=0.5,

    # Auto-terminate settings
    auto_terminate_on_high_severity=True,
    auto_terminate_threshold=3,  # Terminate after 3 high-severity violations
)
```

### Risk Score Calculation

The risk score (0-100) is calculated based on:

- **High severity violations**: +20 points each
- **Medium severity violations**: +10 points each
- **Low severity violations**: +5 points each
- **Face absence ratio**: Up to +30 points
- **Multiple face ratio**: Up to +40 points
- **Look away ratio**: Up to +20 points

### Risk Levels

| Score | Level | Recommendation |
|-------|-------|----------------|
| 0-20 | Low | No significant concerns |
| 20-50 | Medium | Review recommended |
| 50-75 | High | Mandatory review required |
| 75-100 | Critical | Consider invalidating assessment |

## Database Models

### ProctoringSession
Stores complete proctoring session with statistics and risk score.

### ProctoringViolation
Individual violation events with screenshots and review status.

### ProctoringSettings
Configurable settings per task or college.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Browser/Webcam │────▶│  Django Backend  │────▶│  Video Analyzer │
│                 │     │                  │     │  (OpenCV/ML)    │
│  Frame Capture  │     │  REST API        │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │    Database      │
                        │  - Sessions      │
                        │  - Violations    │
                        │  - Settings      │
                        └──────────────────┘
```

## Performance Considerations

1. **Frame Rate**: 1 FPS is typically sufficient for detection
2. **Resolution**: 640x480 provides good balance of quality and performance
3. **Object Detection**: YOLO is optional and requires GPU for real-time performance
4. **Storage**: Screenshots can consume significant storage - configure cleanup

## Privacy & Compliance

- Store only necessary data
- Implement data retention policies
- Obtain user consent before proctoring
- Provide clear privacy policy
- Consider GDPR/regional requirements

## Troubleshooting

### Camera Access Denied
- Ensure HTTPS is enabled (required for camera access)
- Check browser permissions

### Slow Performance
- Reduce frame resolution
- Increase frame interval
- Disable object detection

### False Positives
- Adjust confidence thresholds
- Increase frame thresholds
- Mark false positives in admin panel

## License

MIT License - See LICENSE file for details.
