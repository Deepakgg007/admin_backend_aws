# services_college.py

from django.db.models import Count, Q
from company.models import Company, Concept
from authentication.models import CustomUser
from courses.models import Enrollment, Course
from django.utils import timezone

###############################################################################
# CORE AGGREGATORS (Composable, Testable)
###############################################################################

def get_college_student_stats(college_id: int) -> dict:
    students = CustomUser.objects.filter(college_id=college_id)

    return {
        "total_students": students.count(),
        "approved_students": students.filter(approval_status="approved").count(),
        "pending_students": students.filter(approval_status="pending").count(),
        "rejected_students": students.filter(approval_status="rejected").count(),
    }


def get_college_company_stats(college_id: int) -> dict:
    qs = Company.objects.filter(college_id=college_id)

    industry_distribution = (
        qs.values("industry")
          .annotate(count=Count("id"))
          .order_by("-count")
    )

    return {
        "total_companies": qs.count(),
        "approved_companies": qs.filter(approval_status="APPROVED").count(),
        "pending_companies": qs.filter(approval_status="PENDING").count(),
        "rejected_companies": qs.filter(approval_status="REJECTED").count(),
        "currently_hiring": qs.filter(is_hiring=True).count(),
        "industry_distribution": list(industry_distribution),
        "concepts_count": Concept.objects.filter(company__college_id=college_id).count(),
        "challenges_count": Concept.objects.filter(company__college_id=college_id)
                                          .aggregate(total=Count("challenges__id", distinct=True))
                                          .get("total") or 0,
    }


def get_college_course_stats(college_id: int) -> dict:
    """
    Assumes courses are global, but enrollment ties students to college
    """
    enrollments = Enrollment.objects.filter(student__college_id=college_id)

    # Group by course for pie chart
    distribution = (
        enrollments.values("course__title")
                   .annotate(count=Count("id"))
                   .order_by("-count")
    )

    return {
        "total_courses": Course.objects.count(),
        "unique_enrolled_students": enrollments.values("student_id").distinct().count(),
        "course_distribution": list(distribution),
        "top_courses": list(distribution[:5]),
    }


###############################################################################
# QUICK ACTION INSIGHTS (Dashboard CTA Cards)
###############################################################################

def get_quick_actions(college_id: int) -> list:
    pending_students = CustomUser.objects.filter(
        college_id=college_id,
        approval_status="pending"
    ).count()

    pending_companies = Company.objects.filter(
        college_id=college_id,
        approval_status="PENDING"
    ).count()

    hiring_closing_soon = Company.objects.filter(
        college_id=college_id,
        is_hiring=True,
        hiring_period_end__lte=(timezone.now().date() + timezone.timedelta(days=7))
    ).count()

    return [
        {
            "label": "Review Pending Students",
            "count": pending_students,
            "action": "/college/students/?status=pending"
        },
        {
            "label": "Review Company Approvals",
            "count": pending_companies,
            "action": "/college/companies/?status=pending"
        },
        {
            "label": "Hiring Ending Soon",
            "count": hiring_closing_soon,
            "action": "/college/companies/?filter=hiring_end"
        },
    ]


###############################################################################
# ENTRYPOINT: MAIN DASHBOARD PAYLOAD
###############################################################################

def get_college_dashboard(college_id: int) -> dict:
    """
    Single payload delivered to FE for dashboard rendering
    Cached upstream on the view-layer
    """

    return {
        "students": get_college_student_stats(college_id),
        "companies": get_college_company_stats(college_id),
        "courses": get_college_course_stats(college_id),
        "quick_actions": get_quick_actions(college_id),
    }
