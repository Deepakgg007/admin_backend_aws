# services_student.py

from django.db.models import (
    Count, Avg, F, FloatField, ExpressionWrapper, Q, Case, When, IntegerField
)
from authentication.models import CustomUser
from courses.models import Enrollment, Course
from student.models import CodingChallengeSubmission
from course_cert.models import CertificationAttempt


###############################################################################
# STUDENT CORE PROFILE
###############################################################################
def get_student_profile(user_id: int) -> dict:
    student = (
        CustomUser.objects.select_related("college")
        .only(
            "id", "first_name", "last_name", "email",
            "usn", "profile_picture", "college",
            "approval_status", "is_verified", "created_at"
        )
        .get(id=user_id)
    )

    return {
        "id": student.id,
        "name": student.get_full_name(),
        "email": student.email,
        "usn": student.usn,
        "profile_picture": student.profile_picture.url if student.profile_picture else None,
        "approval_status": student.approval_status,
        "is_verified": student.is_verified,
        "created_at": student.created_at,
        "college": student.college.name if student.college else None,
    }


###############################################################################
# COURSES SUMMARY + COMPLETION %
###############################################################################
def get_student_course_stats(user_id: int) -> dict:
    enrollments = Enrollment.objects.filter(student_id=user_id)

    total = enrollments.count()
    completed = enrollments.filter(status="completed").count()
    active = enrollments.filter(status="in_progress").count()

    completion_rate = round((completed / total) * 100, 2) if total else 0

    return {
        "total_courses": total,
        "active": active,
        "completed": completed,
        "completion_rate": completion_rate,
    }


###############################################################################
# CODING CHALLENGE INSIGHTS
###############################################################################
def get_student_challenge_stats(user_id: int) -> dict:
    qs = CodingChallengeSubmission.objects.filter(user_id=user_id)

    return {
        "total": qs.count(),
        "best_score": qs.aggregate(Avg("score")).get("score__avg") or 0,
        "passed": qs.filter(passed_tests=F("total_tests")).count(),
    }


from django.db.models import (
    F, Q, Avg, Count, FloatField
)
from django.db.models.functions import Cast


###############################################################################
# COMPANY READINESS SCORE
###############################################################################
def get_company_readiness(user_id: int) -> dict:
    """
    Calculate company readiness based on:
    - Challenge completion rate
    - Average test pass rate
    - Problem-solving consistency
    - Difficulty level progression
    """
    submissions = CodingChallengeSubmission.objects.filter(user_id=user_id)

    # -----------------------------------------------------------------------
    # No submissions yet → beginner profile
    # -----------------------------------------------------------------------
    if not submissions.exists():
        return {
            "readiness_score": 0,
            "readiness_level": "Beginner",
            "strengths": [],
            "areas_to_improve": ["Start solving coding challenges"],
            "recommended_action": "Begin with easy challenges to build foundation",
            "metrics": {
                "total_solved": 0,
                "success_rate": 0,
                "avg_test_pass_rate": 0,
                "consistency_score": 0,
            },
        }

    # -----------------------------------------------------------------------
    # Core metrics
    # -----------------------------------------------------------------------
    total_submissions = submissions.count()
    fully_passed = submissions.filter(passed_tests=F("total_tests")).count()

    # Success rate (% of fully passed challenges)
    success_rate = (fully_passed / total_submissions * 100) if total_submissions else 0

    # -----------------------------------------------------------------------
    # Average test pass rate and score (with type safety)
    # -----------------------------------------------------------------------
    avg_stats = submissions.aggregate(
        avg_passed=Avg(Cast("passed_tests", FloatField())),
        avg_total=Avg(Cast("total_tests", FloatField())),
        avg_score=Avg(Cast("score", FloatField())),
    )

    avg_passed = avg_stats["avg_passed"] or 0
    avg_total = avg_stats["avg_total"] or 0
    avg_score = avg_stats["avg_score"] or 0

    avg_test_pass_rate = (avg_passed / avg_total * 100) if avg_total > 0 else 0

    # -----------------------------------------------------------------------
    # Consistency score (based on last 10 submissions)
    # -----------------------------------------------------------------------
    recent_submissions = list(submissions.order_by("-submitted_at")[:10])
    if recent_submissions:
        # Count only successful ones (passed_tests == total_tests)
        recent_success = sum(
            1 for s in recent_submissions if s.passed_tests == s.total_tests
        )
        consistency_score = (recent_success / len(recent_submissions)) * 100
    else:
        consistency_score = 0


    # -----------------------------------------------------------------------
    # Difficulty progression (optional)
    # -----------------------------------------------------------------------
    difficulty_breakdown = submissions.values("challenge__difficulty").annotate(
        total=Count("id"),
        passed=Count("id", filter=Q(passed_tests=F("total_tests"))),
    )

    # -----------------------------------------------------------------------
    # Weighted readiness score
    # -----------------------------------------------------------------------
    readiness_score = round(
        success_rate * 0.35
        + avg_test_pass_rate * 0.25
        + consistency_score * 0.20
        + min(avg_score, 100) * 0.20,
        2,
    )

    # -----------------------------------------------------------------------
    # Readiness level mapping
    # -----------------------------------------------------------------------
    if readiness_score >= 80:
        readiness_level, level_color = "Industry Ready", "success"
    elif readiness_score >= 60:
        readiness_level, level_color = "Interview Ready", "primary"
    elif readiness_score >= 40:
        readiness_level, level_color = "Developing", "warning"
    else:
        readiness_level, level_color = "Beginner", "info"

    # -----------------------------------------------------------------------
    # Strengths and improvement areas
    # -----------------------------------------------------------------------
    strengths, areas_to_improve = [], []

    if success_rate >= 70:
        strengths.append(f"High success rate ({success_rate:.1f}%)")
    elif success_rate < 50:
        areas_to_improve.append("Improve problem-solving success rate")

    if consistency_score >= 70:
        strengths.append("Consistent performance")
    elif consistency_score < 50:
        areas_to_improve.append("Practice more regularly for consistency")

    if avg_test_pass_rate >= 80:
        strengths.append("Strong test case handling")
    elif avg_test_pass_rate < 60:
        areas_to_improve.append("Focus on edge cases and test coverage")

    if total_submissions >= 50:
        strengths.append(f"Extensive practice ({total_submissions} challenges)")
    elif total_submissions < 20:
        areas_to_improve.append("Solve more challenges to build experience")

    # -----------------------------------------------------------------------
    # Recommended action
    # -----------------------------------------------------------------------
    if readiness_score >= 80:
        recommended_action = (
            "You're ready! Start applying to companies and practice mock interviews."
        )
    elif readiness_score >= 60:
        recommended_action = (
            "Focus on medium-hard problems and time-constrained practice."
        )
    elif readiness_score >= 40:
        recommended_action = (
            "Build consistency by solving at least 3 challenges per week."
        )
    else:
        recommended_action = (
            "Start with fundamentals: arrays, strings, and basic algorithms."
        )

    # -----------------------------------------------------------------------
    # Final response
    # -----------------------------------------------------------------------
    return {
        "readiness_score": readiness_score,
        "readiness_level": readiness_level,
        "level_color": level_color,
        "strengths": strengths,
        "areas_to_improve": areas_to_improve,
        "recommended_action": recommended_action,
        "metrics": {
            "total_solved": total_submissions,
            "fully_passed": fully_passed,
            "success_rate": round(success_rate, 2),
            "avg_test_pass_rate": round(avg_test_pass_rate, 2),
            "avg_score": round(avg_score, 2),
            "consistency_score": round(consistency_score, 2),
        },
        "difficulty_breakdown": list(difficulty_breakdown) if difficulty_breakdown else [],
    }


###############################################################################
# CERTIFICATION SUMMARY
###############################################################################
def get_student_certification_stats(user_id: int) -> dict:
    attempts = CertificationAttempt.objects.filter(user_id=user_id)

    avg_score = attempts.aggregate(Avg("score")).get("score__avg") or 0

    return {
        "total_attempts": attempts.count(),
        "certified": attempts.filter(passed=True).count(),
        "avg_score": round(avg_score, 2),
    }


###############################################################################
# STUDENT COLLEGE RANKING
###############################################################################
def get_student_rank(user_id: int) -> dict:
    student = CustomUser.objects.get(id=user_id)
    college_id = student.college_id

    # Completion rate per student
    enrollments = (
        Enrollment.objects.filter(student__college_id=college_id)
        .values("student_id")
        .annotate(
            completed=Count("id", filter=Q(status="completed")),
            total=Count("id"),
        )
    )

    completion_map = {
        e["student_id"]: (e["completed"] * 100.0 / e["total"]) if e["total"] else 0
        for e in enrollments
    }

    # Certification score per student
    cert_scores = (
        CertificationAttempt.objects.values("user_id")
        .annotate(avg_score=Avg("score"))
    )
    cert_map = {c["user_id"]: c["avg_score"] or 0 for c in cert_scores}

    # Annotate users
    students = (
        CustomUser.objects.filter(college_id=college_id)
        .only("id", "first_name", "last_name")
    )

    ranked = []
    for s in students:
        ranked.append({
            "id": s.id,
            "name": s.get_full_name(),
            "completion_rate": completion_map.get(s.id, 0),
            "avg_cert_score": cert_map.get(s.id, 0),
        })

    # Weighting
    for r in ranked:
        r["final_score"] = r["completion_rate"] * 0.6 + r["avg_cert_score"] * 0.4

    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    # Calculate rank
    rank = next((i + 1 for i, r in enumerate(ranked) if r["id"] == user_id), None)

    leaderboard = ranked[:5]

    return {
        "rank": rank,
        "total_students": len(ranked),
        "leaderboard": leaderboard,
    }


###############################################################################
# CTA QUICK ACTIONS
###############################################################################
def get_quick_actions(user_id: int) -> list:
    active_courses = Enrollment.objects.filter(student_id=user_id, status="in_progress").count()
    pending_certs = CertificationAttempt.objects.filter(user_id=user_id, passed=False).count()

    return [
        {"label": "Finish Courses", "value": active_courses, "action": "/courses"},
        {"label": "Continue Certifications", "value": pending_certs, "action": "/certifications"},
        {"label": "Practice Challenges", "value": 1, "action": "/challenges"},
    ]


###############################################################################
# STUDENT SUBMISSION STATS (For College Admin Dashboard)
###############################################################################
def get_student_submission_stats(user_id: int) -> dict:
    """
    Get submission stats for a specific student
    Used by college admins to view student performance
    """
    from student.models import CodingChallengeSubmission, CompanyChallengeSubmission

    # Get coding challenge submissions
    coding_submissions = CodingChallengeSubmission.objects.filter(user_id=user_id)
    coding_attempted = coding_submissions.values('challenge_id').distinct().count()
    coding_solved = coding_submissions.filter(status='ACCEPTED', is_best_submission=True).count()
    coding_failed = coding_submissions.filter(
        status__in=['REJECTED', 'FAILED'],
        is_best_submission=True
    ).count()
    coding_success_rate = round(
        (coding_solved / coding_attempted * 100) if coding_attempted > 0 else 0,
        2
    )

    # Get company challenge submissions
    company_submissions = CompanyChallengeSubmission.objects.filter(user_id=user_id)
    company_attempted = company_submissions.values('challenge_id').distinct().count()
    company_solved = company_submissions.filter(status='ACCEPTED', is_best_submission=True).count()
    company_failed = company_submissions.filter(
        status__in=['REJECTED', 'FAILED'],
        is_best_submission=True
    ).count()
    company_success_rate = round(
        (company_solved / company_attempted * 100) if company_attempted > 0 else 0,
        2
    )

    return {
        "coding_challenges": {
            "attempted": coding_attempted,
            "solved": coding_solved,
            "failed": coding_failed,
            "success_rate": coding_success_rate,
        },
        "company_challenges": {
            "attempted": company_attempted,
            "solved": company_solved,
            "failed": company_failed,
            "success_rate": company_success_rate,
        }
    }


###############################################################################
# ENTRYPOINT (MAIN DASHBOARD)
###############################################################################
def get_student_dashboard(user_id: int) -> dict:
    return {
        "profile": get_student_profile(user_id),
        "courses": get_student_course_stats(user_id),
        "challenges": get_student_challenge_stats(user_id),
        "company_readiness": get_company_readiness(user_id),
        "certifications": get_student_certification_stats(user_id),
        "ranking": get_student_rank(user_id),
        "quick_actions": get_quick_actions(user_id),
    }