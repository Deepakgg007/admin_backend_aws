# Z1_solution - Django Backend API

## Overview
Django 5.0.1 REST API backend for multi-college educational platform with JWT authentication, course management, and Docker-based code execution.

## Tech Stack
- **Django** 5.0.1 + **DRF** 3.14.0
- **MySQL** Database
- **JWT** Authentication (SimpleJWT)
- **Docker** Containerization
- **Swagger/ReDoc** API Documentation

## Quick Start

### Using Docker
```bash
docker-compose up
# Backend runs on http://localhost:1122
```

### Manual Setup
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:1122
```

## Environment Variables
Create `.env` file:
```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.17

DB_NAME=z1_database
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306

JWT_SECRET_KEY=jwt-secret
JWT_ACCESS_TOKEN_LIFETIME=60
JWT_REFRESH_TOKEN_LIFETIME=1440
```

## Django Apps

### 1. **api/** - Organization Management
- Universities, Organizations, Colleges
- Admin-only CRUD operations

### 2. **authentication/** - User Management
- Custom user model with college association
- JWT login/register/profile
- Role-based permissions

### 3. **courses/** - Course System
- Courses, Syllabi, Topics, Tasks
- Content types: Documents, Videos, Questions, Rich Text
- College-specific filtering
- Progress tracking

### 4. **college/** - College Operations
- College-specific endpoints
- Student approval workflow

### 5. **student/** - Student Features
- Student profiles
- Course enrollments
- Progress tracking
- Leaderboard

### 6. **company/** - Company Management
- Company profiles
- Job postings
- Coding challenges

### 7. **coding/** - Code Execution
- Docker-based code runner
- Multi-language support
- Test case validation

## API Endpoints

### Authentication
```
POST   /api/auth/login/          # Login (returns JWT tokens)
POST   /api/auth/register/       # Register new user
GET    /api/auth/profile/        # Get user profile
```

### Courses
```
GET    /api/courses/courses/             # List courses (filtered by college)
POST   /api/courses/courses/             # Create course
GET    /api/courses/courses/{id}/        # Course details
PUT    /api/courses/courses/{id}/        # Update course
DELETE /api/courses/courses/{id}/        # Delete course
```

### College Admin
```
POST   /api/college/login/                   # College admin login
GET    /api/college/students/?status=pending # Get pending students
POST   /api/college/students/{id}/approve/   # Approve student
POST   /api/college/students/{id}/decline/   # Decline student
```

### Coding Challenges
```
POST   /api/coding/execute/      # Execute code
GET    /api/coding/challenges/   # List challenges
POST   /api/coding/submit/       # Submit solution
```

## API Documentation
- **Swagger UI**: http://localhost:1122/api/docs/
- **ReDoc**: http://localhost:1122/api/redoc/
- **Schema**: http://localhost:1122/api/schema/

## Key Features

### Multi-College Architecture
- Colleges are isolated with their own courses
- Students see courses from their college + admin-created courses
- College admins can only manage their college's content

### Role-Based Access
- **Superuser**: Full system access
- **Staff**: Admin privileges (create/edit content)
- **College Admin**: College-specific management
- **Student**: Course enrollment and learning

### Code Execution Engine
- Docker-isolated execution environment
- Support for Python, JavaScript, Java, C++, etc.
- Visible and hidden test cases
- Security-focused design

## Database Models

### Key Models
- `CustomUser` - Extended user with college association
- `University`, `Organization`, `College` - Organizational hierarchy
- `Course`, `Syllabus`, `Topic`, `Task` - Course structure
- `TaskDocument`, `TaskVideo`, `TaskQuestion`, `TaskRichTextPage` - Content types
- `StudentProfile` - Student details and progress
- `CodingChallenge`, `TestCase` - Coding problems

## Permissions
- `IsAdminUserOrReadOnly` - Write access for staff/superuser
- `IsSuperUserOnly` - Superuser-exclusive operations
- College-based filtering in querysets

## Development

### Create Superuser
```bash
python manage.py createsuperuser
```

### Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Admin Panel
Access at http://localhost:1122/admin/

## Troubleshooting

### Database Connection Issues
- Verify MySQL is running
- Check database credentials in `.env`
- Ensure database exists: `CREATE DATABASE z1_database;`

### CORS Errors
- Add frontend URL to `CORS_ALLOWED_ORIGINS` in settings
- Check `ALLOWED_HOSTS` includes your IP

### Code Execution Issues
- Ensure Docker is running
- Check Docker socket permissions
- Review `coding/executor.py` logs

## Project Structure
```
Z1_solution/
├── api/                  # Organization management
├── authentication/       # User & auth
├── courses/             # Course system
├── college/             # College operations
├── student/             # Student features
├── company/             # Company management
├── coding/              # Code execution
├── media/               # Uploaded files
├── z1_backend/          # Django settings
├── manage.py
├── requirements.txt
└── docker-compose.yml
```

## License
Proprietary - Educational Platform Project
