/**
 * Video Proctoring Client
 * =======================
 *
 * JavaScript/TypeScript client for integrating video proctoring
 * with online quizzes and assessments.
 *
 * Features:
 * - Webcam access and frame capture
 * - Real-time frame streaming to backend
 * - Violation alerts
 * - Session management
 *
 * Usage:
 *   const proctor = new VideoProctoringClient({
 *     apiBaseUrl: 'https://api.example.com/proctoring',
 *     taskId: 'quiz-uuid',
 *     onViolation: (violation) => console.log(violation),
 *   });
 *
 *   await proctor.startSession();
 *   // Quiz in progress...
 *   await proctor.endSession();
 */

class VideoProctoringClient {
    /**
     * Initialize the proctoring client
     * @param {Object} options - Configuration options
     * @param {string} options.apiBaseUrl - Base URL for proctoring API
     * @param {string} options.taskId - UUID of the quiz/task
     * @param {Function} options.onViolation - Callback for violation events
     * @param {Function} options.onError - Callback for error events
     * @param {number} options.frameInterval - Interval between frame captures (ms)
     * @param {number} options.videoWidth - Video capture width
     * @param {number} options.videoHeight - Video capture height
     */
    constructor(options = {}) {
        this.apiBaseUrl = options.apiBaseUrl || '/api/proctoring';
        this.taskId = options.taskId;
        this.onViolation = options.onViolation || (() => {});
        this.onError = options.onError || console.error;
        this.onWarning = options.onWarning || console.warn;
        this.onStatusChange = options.onStatusChange || (() => {});

        this.frameInterval = options.frameInterval || 1000; // 1 second default
        this.videoWidth = options.videoWidth || 640;
        this.videoHeight = options.videoHeight || 480;

        this.sessionId = null;
        this.videoStream = null;
        this.videoElement = null;
        this.canvasElement = null;
        this.canvasContext = null;
        this.frameNumber = 0;
        this.captureInterval = null;
        this.isActive = false;
        this.lastViolationTime = 0;

        // Performance tracking
        this.framesCaptured = 0;
        this.framesFailed = 0;
        this.startTime = null;
    }

    /**
     * Start the proctoring session
     * @returns {Promise<Object>} Session info
     */
    async startSession() {
        try {
            // 1. Request camera access
            this.videoStream = await this._requestCameraAccess();

            // 2. Setup video element
            this._setupVideoElement();

            // 3. Setup canvas for frame capture
            this._setupCanvas();

            // 4. Capture reference frame
            const referenceFrame = await this._captureFrame();

            // 5. Create session on backend
            const response = await this._apiRequest('/sessions/', 'POST', {
                task_id: this.taskId,
                reference_frame: referenceFrame,
            });

            this.sessionId = response.session_id;
            this.isActive = true;
            this.startTime = Date.now();
            this.onStatusChange('active');

            // 6. Start frame capture loop
            this._startFrameCapture();

            console.log('Proctoring session started:', this.sessionId);
            return response;

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * End the proctoring session
     * @returns {Promise<Object>} Session summary
     */
    async endSession() {
        if (!this.sessionId) {
            throw new Error('No active session');
        }

        try {
            // Stop frame capture
            this._stopFrameCapture();

            // End session on backend
            const response = await this._apiRequest(
                `/sessions/${this.sessionId}/end/`,
                'POST'
            );

            // Cleanup
            this._cleanup();

            this.isActive = false;
            this.onStatusChange('completed');

            console.log('Proctoring session ended:', response);
            return response;

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * Get current session status
     * @returns {Promise<Object>} Status info
     */
    async getStatus() {
        if (!this.sessionId) {
            return { active: false };
        }

        const response = await this._apiRequest(
            `/sessions/${this.sessionId}/status/`,
            'GET'
        );

        return response;
    }

    /**
     * Get risk assessment
     * @returns {Promise<Object>} Risk assessment
     */
    async getRiskAssessment() {
        if (!this.sessionId) {
            throw new Error('No active session');
        }

        const response = await this._apiRequest(
            `/risk-assessment/${this.sessionId}/`,
            'GET'
        );

        return response;
    }

    // =====================
    // Private Methods
    // =====================

    async _requestCameraAccess() {
        const constraints = {
            video: {
                width: { ideal: this.videoWidth },
                height: { ideal: this.videoHeight },
                facingMode: 'user',
            },
            audio: false,
        };

        try {
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            return stream;
        } catch (error) {
            if (error.name === 'NotAllowedError') {
                throw new Error('Camera access denied. Please allow camera access to continue.');
            } else if (error.name === 'NotFoundError') {
                throw new Error('No camera found. Please connect a camera and try again.');
            }
            throw error;
        }
    }

    _setupVideoElement() {
        this.videoElement = document.createElement('video');
        this.videoElement.srcObject = this.videoStream;
        this.videoElement.setAttribute('playsinline', '');
        this.videoElement.muted = true;

        // Optionally add to DOM for preview
        // document.body.appendChild(this.videoElement);

        return new Promise((resolve) => {
            this.videoElement.onloadedmetadata = () => {
                this.videoElement.play();
                resolve();
            };
        });
    }

    _setupCanvas() {
        this.canvasElement = document.createElement('canvas');
        this.canvasElement.width = this.videoWidth;
        this.canvasElement.height = this.videoHeight;
        this.canvasContext = this.canvasElement.getContext('2d');
    }

    async _captureFrame() {
        return new Promise((resolve, reject) => {
            try {
                // Draw video frame to canvas
                this.canvasContext.drawImage(
                    this.videoElement,
                    0, 0,
                    this.videoWidth,
                    this.videoHeight
                );

                // Convert to base64
                const dataUrl = this.canvasElement.toDataURL('image/jpeg', 0.7);

                this.frameNumber++;
                this.framesCaptured++;

                resolve({
                    data: dataUrl,
                    frameNumber: this.frameNumber,
                });

            } catch (error) {
                this.framesFailed++;
                reject(error);
            }
        });
    }

    async _sendFrame(frameData) {
        try {
            const response = await this._apiRequest('/analyze-frame/', 'POST', {
                session_id: this.sessionId,
                frame_data: frameData.data,
                frame_number: frameData.frameNumber,
                timestamp: (Date.now() - this.startTime) / 1000,
            });

            // Handle violations
            if (response.violation_detected) {
                const now = Date.now();
                // Debounce violations (don't spam)
                if (now - this.lastViolationTime > 2000) {
                    this.lastViolationTime = now;
                    this.onViolation({
                        type: response.violation_type,
                        severity: response.severity,
                        details: response.details,
                        timestamp: new Date().toISOString(),
                    });
                }
            }

            // Check for session termination
            if (response.session_terminated) {
                this.onWarning({
                    type: 'session_terminated',
                    message: 'Your session has been terminated due to policy violations.',
                });
                await this.endSession();
            }

            return response;

        } catch (error) {
            // Don't throw on frame errors, just log
            console.error('Frame analysis error:', error);
            this.framesFailed++;
        }
    }

    _startFrameCapture() {
        this.captureInterval = setInterval(async () => {
            if (!this.isActive) return;

            try {
                const frame = await this._captureFrame();
                await this._sendFrame(frame);
            } catch (error) {
                console.error('Frame capture error:', error);
            }
        }, this.frameInterval);
    }

    _stopFrameCapture() {
        if (this.captureInterval) {
            clearInterval(this.captureInterval);
            this.captureInterval = null;
        }
    }

    _cleanup() {
        // Stop video stream
        if (this.videoStream) {
            this.videoStream.getTracks().forEach(track => track.stop());
            this.videoStream = null;
        }

        // Remove video element
        if (this.videoElement && this.videoElement.parentNode) {
            this.videoElement.parentNode.removeChild(this.videoElement);
        }

        this.videoElement = null;
        this.canvasElement = null;
        this.canvasContext = null;
    }

    async _apiRequest(endpoint, method, data = null) {
        const url = `${this.apiBaseUrl}${endpoint}`;

        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };

        // Add auth token if available
        const token = this._getAuthToken();
        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(url, options);

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.error || `API Error: ${response.status}`);
        }

        return response.json();
    }

    _getAuthToken() {
        // Override this method or set token directly
        return localStorage.getItem('auth_token') ||
               document.cookie.match(/auth_token=([^;]+)/)?.[1];
    }
}


// =====================
// React Component Hook
// =====================

/**
 * React hook for video proctoring
 *
 * Usage in React component:
 *
 *   const proctor = useVideoProctoring({
 *     taskId: 'quiz-uuid',
 *     autoStart: true,
 *   });
 *
 *   // In your component:
 *   if (proctor.violation) {
 *     return <ViolationAlert violation={proctor.violation} />;
 *   }
 */
function useVideoProctoring(options = {}) {
    const [proctor] = React.useState(() => new VideoProctoringClient(options));
    const [status, setStatus] = React.useState('idle');
    const [violation, setViolation] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [sessionData, setSessionData] = React.useState(null);

    React.useEffect(() => {
        proctor.onStatusChange = setStatus;
        proctor.onViolation = setViolation;
        proctor.onError = setError;

        if (options.autoStart) {
            proctor.startSession()
                .then(setSessionData)
                .catch(setError);
        }

        return () => {
            if (proctor.isActive) {
                proctor.endSession();
            }
        };
    }, []);

    return {
        proctor,
        status,
        violation,
        error,
        sessionData,
        startSession: () => proctor.startSession().then(setSessionData),
        endSession: () => proctor.endSession().then(setSessionData),
        clearViolation: () => setViolation(null),
    };
}


// =====================
// Vue 3 Composable
// =====================

/**
 * Vue 3 composable for video proctoring
 *
 * Usage in Vue component:
 *
 *   const { status, violation, startSession, endSession } = useVideoProctoring({
 *     taskId: props.taskId,
 *   });
 */
function useVideoProctoringVue(options = {}) {
    const proctor = new VideoProctoringClient(options);
    const status = Vue.ref('idle');
    const violation = Vue.ref(null);
    const error = Vue.ref(null);
    const sessionData = Vue.ref(null);

    proctor.onStatusChange = (s) => status.value = s;
    proctor.onViolation = (v) => violation.value = v;
    proctor.onError = (e) => error.value = e;

    const startSession = async () => {
        try {
            const data = await proctor.startSession();
            sessionData.value = data;
            return data;
        } catch (e) {
            error.value = e;
            throw e;
        }
    };

    const endSession = async () => {
        try {
            const data = await proctor.endSession();
            sessionData.value = data;
            return data;
        } catch (e) {
            error.value = e;
            throw e;
        }
    };

    Vue.onUnmounted(() => {
        if (proctor.isActive) {
            proctor.endSession();
        }
    });

    return {
        status,
        violation,
        error,
        sessionData,
        startSession,
        endSession,
        proctor,
    };
}


// =====================
// Plain JavaScript Integration
// =====================

/**
 * Simple integration for non-framework environments
 */
async function initQuizProctoring(config) {
    const proctor = new VideoProctoringClient({
        apiBaseUrl: config.apiBaseUrl,
        taskId: config.taskId,
        onViolation: (violation) => {
            // Show warning to user
            alert(`Warning: ${violation.type.replace(/_/g, ' ')}`);

            // Log to server or display in UI
            if (config.violationContainer) {
                const container = document.getElementById(config.violationContainer);
                container.innerHTML = `
                    <div class="proctoring-warning ${violation.severity}">
                        <strong>${violation.type.replace(/_/g, ' ')}</strong>
                        <p>Severity: ${violation.severity}</p>
                    </div>
                `;
            }

            // Callback for custom handling
            if (config.onViolation) {
                config.onViolation(violation);
            }
        },
        onError: (error) => {
            console.error('Proctoring error:', error);
            if (config.onError) {
                config.onError(error);
            }
        },
    });

    // Start session when quiz begins
    document.getElementById(config.startButtonId)?.addEventListener('click', async () => {
        try {
            await proctor.startSession();
            console.log('Proctoring started');
        } catch (error) {
            alert('Could not start proctoring: ' + error.message);
        }
    });

    // End session when quiz submits
    document.getElementById(config.submitButtonId)?.addEventListener('click', async () => {
        try {
            const summary = await proctor.endSession();
            console.log('Proctoring ended:', summary);

            // Optionally include proctoring data with submission
            if (config.includeWithSubmission) {
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'proctoring_session_id';
                hiddenInput.value = proctor.sessionId;
                document.getElementById(config.formId)?.appendChild(hiddenInput);
            }
        } catch (error) {
            console.error('Error ending proctoring:', error);
        }
    });

    return proctor;
}


// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        VideoProctoringClient,
        useVideoProctoring,
        useVideoProctoringVue,
        initQuizProctoring,
    };
}
