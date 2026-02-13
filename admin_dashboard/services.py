from django.utils import timezone
from django.db.models import Count, Avg, Max, Q
from authentication.models import CustomUser
from api.models import University, Organization, College
from courses.models import Course, Enrollment
from coding.models import Challenge
from student.models import StudentChallengeSubmission
from student.user_profile_models import UserProfile
from course_cert.models import Certification, CertificationAttempt


def get_dashboard_data(college_id=None):
    """
    Enhanced dashboard summary with:
    - Core counts
    - Certification analytics
    - Challenge trends
    - Engagement metrics
    - Optional college filtering for top students and cert students
    """
    # --- User/Student counts ---
    students_qs = CustomUser.objects.filter(is_staff=False, is_superuser=False)

    # Filter by college if provided (for top students filtering)
    if college_id:
        students_filtered_by_college = students_qs.filter(college_id=college_id)
    else:
        students_filtered_by_college = students_qs

    total_students = students_qs.count()

    approval_counts = (
        students_qs.values('approval_status').annotate(count=Count('id'))
    )
    approval_summary = {item['approval_status']: item['count'] for item in approval_counts}

    # --- University, Org, College counts ---
    total_universities = University.objects.count()
    total_organizations = Organization.objects.count()
    total_colleges = College.objects.count()

    # --- Course counts ---
    total_courses = Course.objects.count()
    total_enrolled_students = Enrollment.objects.values('student').distinct().count()

    avg_enrollments_per_student = (
        total_enrolled_students / total_students if total_students > 0 else 0
    )

    # --- Top enrolled courses ---
    most_enrolled_courses_qs = (
        Enrollment.objects.values('course__id', 'course__title')
        .annotate(enroll_count=Count('id'))
        .order_by('-enroll_count')
    )
    most_enrolled_course = most_enrolled_courses_qs.first()

    top_courses_list = [
        {
            "course_id": c.get('course__id'),
            "title": c.get('course__title', 'Unknown'),
            "enrollments": c.get('enroll_count', 0)
        }
        for c in most_enrolled_courses_qs[:5]
    ]
    
    # Ensure most_enrolled_course has proper structure even if None
    if most_enrolled_course:
        most_enrolled_course = {
            "course_id": most_enrolled_course.get('course__id'),
            "title": most_enrolled_course.get('course__title', 'Unknown'),
            "enrollments": most_enrolled_course.get('enroll_count', 0)
        }
    else:
        most_enrolled_course = None

    # --- Coding challenge stats ---
    total_challenges = Challenge.objects.count()
    avg_success_rate = Challenge.objects.aggregate(avg_success=Avg('success_rate'))['avg_success'] or 0
    max_score_challenge = Challenge.objects.aggregate(max_score=Max('max_score'))['max_score'] or 0

    # Weekly challenge submissions trend (8 weeks)
    today = timezone.now().date()
    challenge_trends = []
    for week in range(8):
        start = today - timezone.timedelta(days=today.weekday() + week * 7)
        end = start + timezone.timedelta(days=6)
        submissions = StudentChallengeSubmission.objects.filter(
            submitted_at__date__gte=start,
            submitted_at__date__lte=end
        ).count()
        challenge_trends.append({
            "week_start": start.isoformat() if hasattr(start, 'isoformat') else str(start),
            "week_end": end.isoformat() if hasattr(end, 'isoformat') else str(end),
            "submissions": submissions
        })

    # --- Certifications analytics ---
    total_certifications = Certification.objects.count()
    total_cert_attempts = CertificationAttempt.objects.count()

    # Passed attempts using `passed=True`
    passed_attempts = CertificationAttempt.objects.filter(passed=True).count()
    cert_pass_rate = round(
        (passed_attempts / total_cert_attempts * 100) if total_cert_attempts > 0 else 0,
        2
    )

    # Top scorers - filter by college if provided
    top_cert_students_qs = CertificationAttempt.objects.select_related('user', 'certification').filter(score__isnull=False)

    if college_id:
        top_cert_students_qs = top_cert_students_qs.filter(user__college_id=college_id)

    top_cert_students = top_cert_students_qs.order_by('-score')[:10]

    top_cert_list = [
        {
            "username": att.user.username,
            "full_name": f"{att.user.first_name} {att.user.last_name}",
            "score": att.score,
            "cert_name": att.certification.title,
        } for att in top_cert_students
    ]

    # Active users last 7 days
    week_ago = timezone.now() - timezone.timedelta(days=7)
    active_users = CustomUser.objects.filter(last_login__gte=week_ago).count()

    # --- Top Coding Students - filter by college if provided ---
    top_profiles_qs = UserProfile.objects.select_related('user')

    if college_id:
        top_profiles_qs = top_profiles_qs.filter(user__college_id=college_id)

    top_profiles = top_profiles_qs.order_by('-total_points', '-challenges_solved')[:10]

    top_students = [
        {
            "username": p.user.username,
            "full_name": f"{p.user.first_name} {p.user.last_name}",
            "total_score": p.total_points,
            "problems_solved": p.challenges_solved,
            "current_streak": p.current_streak,
            "max_streak": p.longest_streak,
        } for p in top_profiles
    ]

    # --- Weekly student signup trends ---
    weekly_signup = []
    for week in range(8):
        start = today - timezone.timedelta(days=today.weekday() + week * 7)
        end = start + timezone.timedelta(days=6)
        new_students = students_qs.filter(
            created_at__date__gte=start,
            created_at__date__lte=end
        ).count()
        weekly_signup.append({
            "week_start": start.isoformat() if hasattr(start, 'isoformat') else str(start),
            "week_end": end.isoformat() if hasattr(end, 'isoformat') else str(end),
            "new_students": new_students
        })

    # --- Weekly certification completion trend ---
    weekly_certifications = []
    for week in range(8):
        start = today - timezone.timedelta(days=today.weekday() + week * 7)
        end = start + timezone.timedelta(days=6)
        completed = CertificationAttempt.objects.filter(
            completed_at__date__gte=start,
            completed_at__date__lte=end
        ).count()
        weekly_certifications.append({
            "week_start": start.isoformat() if hasattr(start, 'isoformat') else str(start),
            "week_end": end.isoformat() if hasattr(end, 'isoformat') else str(end),
            "completed": completed
        })

    data = {
        "summary": {
            "total_students": total_students,
            "total_universities": total_universities,
            "total_organizations": total_organizations,
            "total_colleges": total_colleges,
            "total_courses": total_courses,
            "total_enrolled_students": total_enrolled_students,
            "avg_enrollments_per_student": round(avg_enrollments_per_student, 2),
            "most_enrolled_course": most_enrolled_course,
            "top_courses_list": top_courses_list,

            # challenges
            "total_challenges": total_challenges,
            "avg_challenge_success_rate": round(avg_success_rate, 2),
            "max_score_challenge": max_score_challenge,

            # certifications
            "total_certifications": total_certifications,
            "total_cert_attempts": total_cert_attempts,
            "cert_pass_rate": cert_pass_rate,

            # engagement
            "active_users_7_days": active_users,
        },

        "weekly_student_signup": weekly_signup,
        "weekly_challenge_trends": challenge_trends,
        "weekly_certification_trends": weekly_certifications,
        "top_students": top_students,
        "top_cert_students": top_cert_list,
    }

    return data


def get_completion_report(college_id=None):
    """
    Generate course completion report with certificate information
    Returns students who completed courses and their certificate status
    """
    from course_cert.models import CertificationAttempt
    
    # Get all completed enrollments
    enrollments_qs = Enrollment.objects.filter(
        Q(status='completed') | Q(progress_percentage__gte=100)
    ).select_related('student', 'course')
    
    # Filter by college if provided
    if college_id:
        enrollments_qs = enrollments_qs.filter(student__college_id=college_id)
    
    # Get all certification attempts that passed
    passed_attempts = CertificationAttempt.objects.filter(
        passed=True
    ).select_related('user', 'certification', 'certification__course')
    
    if college_id:
        passed_attempts = passed_attempts.filter(user__college_id=college_id)
    
    # Build a map of (user_id, course_id) -> has_certificate
    cert_map = {}
    for attempt in passed_attempts:
        key = (attempt.user_id, attempt.certification.course_id)
        cert_map[key] = True
    
    # Separate completed courses into with and without certificates
    completed_courses = []
    students_with_certs = []
    completed_without_certs = []
    
    for enrollment in enrollments_qs:
        student = enrollment.student
        course = enrollment.course
        
        course_data = {
            'student_id': student.id,
            'student_name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'student_email': student.email,
            'college_name': student.college.name if student.college else '—',
            'course_id': course.id,
            'course_title': course.title,
            'progress_percentage': float(enrollment.progress_percentage or 0),
            'completed_at': enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            'enrolled_at': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
            'duration_hours': course.duration_hours or 0,
        }
        
        # Check if student has certificate for this course
        has_cert = cert_map.get((student.id, course.id), False)
        course_data['has_certificate'] = has_cert
        
        completed_courses.append(course_data)
        
        if has_cert:
            students_with_certs.append(course_data)
        else:
            completed_without_certs.append(course_data)
    
    # Calculate summary statistics
    unique_students_certified = len(set(
        (cert['student_id'], cert['course_id']) for cert in students_with_certs
    ))
    unique_students_completed = len(set(
        (cert['student_id'], cert['course_id']) for cert in completed_courses
    ))
    
    summary = {
        'total_completed_courses': len(completed_courses),
        'total_completed_without_certs': len(completed_without_certs),
        'total_students_with_certs': len(students_with_certs),
        'unique_students_certified': unique_students_certified,
        'unique_students_completed': unique_students_completed,
    }
    
    return {
        'completed_courses': completed_courses,
        'students_with_certificates': students_with_certs,
        'completed_without_certificates': completed_without_certs,
        'students_without_certificates': completed_without_certs,  # Alias for frontend compatibility
        'summary': summary,
    }


def get_students_report(college_id=None):
    """
    Generate student report with performance metrics
    Returns list of students with their statistics
    """
    from student.user_profile_models import UserProfile
    from student.models import StudentChallengeSubmission
    from django.utils import timezone

    # Get all students (non-staff, non-superuser)
    students_qs = CustomUser.objects.filter(
        is_staff=False,
        is_superuser=False
    ).select_related('college')

    # Filter by college if provided
    if college_id:
        students_qs = students_qs.filter(college_id=college_id)

    # Recalculate progress for all enrollments to ensure status is up-to-date
    student_ids = list(students_qs.values_list('id', flat=True))
    all_enrollments = Enrollment.objects.filter(student_id__in=student_ids)

    for enrollment in all_enrollments:
        # Recalculate progress which will update status if needed
        enrollment.calculate_progress()

        # Additional check: Mark any 100% enrollments as completed
        if enrollment.progress_percentage >= 100 and enrollment.status != 'completed':
            enrollment.status = 'completed'
            if not enrollment.completed_at:
                enrollment.completed_at = timezone.now()
            enrollment.save(update_fields=['status', 'completed_at'])
    
    # Get student IDs
    student_ids = list(students_qs.values_list('id', flat=True))
    
    # Bulk get enrollment stats
    enrollment_stats = Enrollment.objects.filter(
        student_id__in=student_ids
    ).values('student_id').annotate(
        total_courses=Count('id'),
        completed_courses=Count('id', filter=Q(status='completed') | Q(progress_percentage__gte=100)),
        total_progress=Avg('progress_percentage')
    )
    enrollment_map = {
        stat['student_id']: {
            'total_courses': stat['total_courses'],
            'completed_courses': stat['completed_courses'],
            'total_progress': float(stat['total_progress'] or 0),
        }
        for stat in enrollment_stats
    }
    
    # Bulk get challenge stats
    challenge_stats = StudentChallengeSubmission.objects.filter(
        user_id__in=student_ids
    ).values('user_id').annotate(
        total_submissions=Count('id'),
        accepted_submissions=Count('id', filter=Q(status='ACCEPTED')),
        challenges_solved=Count('challenge', distinct=True, filter=Q(status='ACCEPTED', is_best_submission=True))
    )
    challenge_map = {
        stat['user_id']: {
            'total_submissions': stat['total_submissions'],
            'accepted_submissions': stat['accepted_submissions'],
            'challenges_solved': stat['challenges_solved'],
        }
        for stat in challenge_stats
    }
    
    students_data = []
    
    for student in students_qs:
        # Get enrollment stats
        enroll_stats = enrollment_map.get(student.id, {
            'total_courses': 0,
            'completed_courses': 0,
            'total_progress': 0,
        })
        
        total_courses = enroll_stats['total_courses']
        completed_courses = enroll_stats['completed_courses']
        completion_percentage = round(enroll_stats['total_progress'], 2) if total_courses > 0 else 0
        
        # Get challenge stats
        challenge_stats_data = challenge_map.get(student.id, {
            'total_submissions': 0,
            'accepted_submissions': 0,
            'challenges_solved': 0,
        })
        
        total_submissions = challenge_stats_data['total_submissions']
        accepted_submissions = challenge_stats_data['accepted_submissions']
        challenges_solved = challenge_stats_data['challenges_solved']
        
        # Success rate
        success_rate = round(
            (accepted_submissions / total_submissions * 100) if total_submissions > 0 else 0,
            2
        )
        
        student_data = {
            'id': student.id,
            'name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'email': student.email,
            'college_name': student.college.name if student.college else None,
            'challenges_solved': challenges_solved,
            'success_rate': success_rate,
            'total_courses': total_courses,
            'courses_completed': completed_courses,
            'completion_percentage': completion_percentage,
        }

        students_data.append(student_data)

    return students_data


def get_student_details(student_id):
    """
    Get detailed information about a specific student including:
    - Profile info
    - Enrolled courses with progress
    - Coding challenge submissions
    - Certifications
    """
    from django.contrib.auth import get_user_model
    from student.user_profile_models import UserProfile
    from student.models import StudentChallengeSubmission
    from course_cert.models import CertificationAttempt

    User = get_user_model()

    try:
        student = User.objects.get(id=student_id)
    except User.DoesNotExist:
        return None

    # Get user profile if exists
    try:
        profile = UserProfile.objects.get(user=student)
        profile_data = {
            'total_points': profile.total_points,
            'challenges_solved': profile.challenges_solved,
            'current_streak': profile.current_streak,
            'longest_streak': profile.longest_streak,
            'rank': profile.rank,
        }
    except UserProfile.DoesNotExist:
        profile_data = {
            'total_points': 0,
            'challenges_solved': 0,
            'current_streak': 0,
            'longest_streak': 0,
            'rank': 'Beginner',
        }

    # Get enrolled courses
    enrollments = Enrollment.objects.filter(
        student=student
    ).select_related('course').order_by('-enrolled_at')

    courses_data = []
    for enrollment in enrollments:
        course = enrollment.course
        courses_data.append({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description,
            'thumbnail': course.thumbnail.url if course.thumbnail else None,
            'status': enrollment.status,
            'progress_percentage': float(enrollment.progress_percentage or 0),
            'enrolled_at': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
            'completed_at': enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            'last_accessed': enrollment.last_accessed.isoformat() if enrollment.last_accessed else None,
        })

    # Get coding challenge submissions
    challenge_submissions = StudentChallengeSubmission.objects.filter(
        user=student
    ).select_related('challenge').order_by('-submitted_at')

    coding_challenges = []
    for submission in challenge_submissions:
        challenge = submission.challenge
        coding_challenges.append({
            'id': challenge.id,
            'title': challenge.title,
            'difficulty': challenge.difficulty,
            'category': challenge.category,
            'status': submission.status,
            'score': submission.score,
            'max_score': submission.max_score or challenge.max_score,
            'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None,
            'is_best_submission': submission.is_best_submission,
        })

    # Get certifications
    cert_attempts = CertificationAttempt.objects.filter(
        user=student
    ).select_related('certification').order_by('-completed_at')

    certifications = []
    for attempt in cert_attempts:
        certifications.append({
            'id': attempt.certification.id,
            'title': attempt.certification.title,
            'score': attempt.score,
            'passed': attempt.passed,
            'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
        })

    # Build response
    return {
        'id': student.id,
        'name': f"{student.first_name} {student.last_name}".strip() or student.username,
        'email': student.email,
        'username': student.username,
        'phone_number': student.phone_number,
        'usn': student.usn,
        'profile_pic': student.profile_picture.url if student.profile_picture else None,
        'college': {
            'id': student.college.id if student.college else None,
            'name': student.college.name if student.college else student.college_name or 'N/A',
        } if student.college or student.college_name else None,
        'status': student.approval_status or 'active',
        'is_verified': student.is_verified,
        'created_at': student.created_at.isoformat() if student.created_at else None,
        'last_login': student.last_login.isoformat() if student.last_login else None,
        # Profile stats
        'profile': profile_data,
        # Courses
        'courses': courses_data,
        'courses_count': len(courses_data),
        'courses_completed': sum(1 for c in courses_data if c['status'] == 'completed'),
        'courses_in_progress': sum(1 for c in courses_data if c['status'] == 'in_progress'),
        # Coding challenges
        'coding_challenges': coding_challenges,
        'coding_challenges_count': len(coding_challenges),
        'challenges_solved': profile_data['challenges_solved'],
        # Certifications
        'certifications': certifications,
        'certifications_count': len(certifications),
        'certifications_passed': sum(1 for c in certifications if c['passed']),
    }
