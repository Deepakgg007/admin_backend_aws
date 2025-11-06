# Student App - API Documentation

## Overview
The `student` app provides APIs for student users to submit code solutions for coding challenges and track their progress.

## Model: StudentChallengeSubmission

### Fields
- `user` - ForeignKey to User (auto-set from authenticated user)
- `challenge` - ForeignKey to Challenge
- `submitted_code` - Text field for code submission
- `language` - Choice field (python, java, c_cpp, c, javascript)
- `status` - Choice field (PENDING, ACCEPTED, WRONG_ANSWER, RUNTIME_ERROR, etc.)
- `passed_tests` - Integer (number of test cases passed)
- `total_tests` - Integer (total number of test cases)
- `score` - Integer
- `runtime` - Float (in milliseconds)
- `memory_used` - Float (in KB)
- `test_results` - JSONField (detailed test case results)
- `compilation_message` - TextField
- `is_best_submission` - Boolean
- `submitted_at` - DateTime (auto)

## API Endpoints

### Base URL: `/api/student/`

### 1. List Submissions
**GET** `/api/student/submissions/`

Query Parameters:
- `challenge` - Filter by challenge slug
- `status` - Filter by status (ACCEPTED, PENDING, etc.)

Response: List of submissions for authenticated user

### 2. Create Submission
**POST** `/api/student/submissions/`

Request Body:
```json
{
  "challenge": 1,
  "submitted_code": "def solution():\n    pass",
  "language": "python"
}
```

Response: Created submission with status PENDING

### 3. Get Submission Detail
**GET** `/api/student/submissions/{id}/`

Response: Full submission details

### 4. My Submissions
**GET** `/api/student/submissions/my_submissions/`

Response: All submissions for current user

### 5. Statistics
**GET** `/api/student/submissions/statistics/`

Response:
```json
{
  "total_submissions": 50,
  "accepted": 30,
  "wrong_answer": 10,
  "runtime_error": 5,
  "compilation_error": 3,
  "time_limit_exceeded": 2,
  "problems_solved": 25,
  "total_score": 2500,
  "average_score": 83.3
}
```

### 6. Submissions by Challenge
**GET** `/api/student/submissions/by-challenge/{challenge_slug}/`

Response: All submissions for specific challenge

### 7. Recent Submissions
**GET** `/api/student/submissions/recent/`

Response: Last 10 submissions

## Permissions
- All endpoints require authentication
- Students can only view/create their own submissions
- Admin users can view all submissions via Django admin

## Usage in Frontend

### Submit Code
```javascript
const response = await axios.post(
  `${API_BASE_URL}/api/student/submissions/`,
  {
    challenge: challengeId,
    submitted_code: code,
    language: selectedLanguage
  },
  {
    headers: { Authorization: `Bearer ${authToken}` }
  }
);
```

### Get Statistics
```javascript
const response = await axios.get(
  `${API_BASE_URL}/api/student/submissions/statistics/`,
  {
    headers: { Authorization: `Bearer ${authToken}` }
  }
);
```

### View Submissions for Challenge
```javascript
const response = await axios.get(
  `${API_BASE_URL}/api/student/submissions/?challenge=${challengeSlug}`,
  {
    headers: { Authorization: `Bearer ${authToken}` }
  }
);
```

## TODO
- Integrate with code execution engine (Judge0, etc.) to evaluate submissions
- Add real-time feedback for code execution
- Implement test case results in detail
- Add code plagiarism detection
- Add submission history timeline
