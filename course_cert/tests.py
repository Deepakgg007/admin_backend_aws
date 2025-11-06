import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from courses.models import Enrollment
from course_cert.models import (
    Certification,
    CertificationQuestion,
    CertificationOption,
    CertificationAttempt,
    AttemptAnswer
)

pytestmark = pytest.mark.django_db

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def setup_certification(django_user_model):
    """Create test data for certification + student + course enrollment."""
    user = django_user_model.objects.create_user(username="student1", password="test123")
    course = user.enrollments.create(course_name="Django Course")  # adapt if your model differs

    cert = Certification.objects.create(
        course=course.course,
        title="Django Basics",
        passing_score=50,
        duration_minutes=60,
        max_attempts=2
    )

    q1 = CertificationQuestion.objects.create(
        certification=cert,
        text="What is Django?",
        weight=10
    )
    o1 = CertificationOption.objects.create(question=q1, text="A Python framework", is_correct=True)
    o2 = CertificationOption.objects.create(question=q1, text="A JS library", is_correct=False)
    return user, cert, q1, [o1, o2]


def authenticate(client, user):
    client.force_authenticate(user)
    return client


def test_start_first_attempt(api_client, setup_certification):
    """✅ Student starts their first attempt."""
    user, cert, q1, options = setup_certification
    client = authenticate(api_client, user)

    res = client.post("/api/student/cert/attempts/start/", {"certification": cert.id})
    assert res.status_code == 201
    data = res.json()
    assert data["attempt_number"] == 1
    assert not data["resumed"]


def test_resume_incomplete_attempt(api_client, setup_certification):
    """✅ Should resume existing incomplete attempt."""
    user, cert, q1, _ = setup_certification
    attempt = CertificationAttempt.objects.create(user=user, certification=cert, attempt_number=1)
    client = authenticate(api_client, user)

    res = client.post("/api/student/cert/attempts/start/", {"certification": cert.id})
    assert res.status_code == 200
    data = res.json()
    assert data["resumed"]
    assert data["attempt_number"] == attempt.attempt_number


def test_expired_attempt_allows_new(api_client, setup_certification):
    """✅ Expired attempt should allow new attempt creation."""
    user, cert, q1, _ = setup_certification
    attempt = CertificationAttempt.objects.create(
        user=user,
        certification=cert,
        attempt_number=1,
        started_at=timezone.now() - timedelta(minutes=cert.duration_minutes + 10)
    )
    client = authenticate(api_client, user)

    res = client.post("/api/student/cert/attempts/start/", {"certification": cert.id})
    assert res.status_code == 201
    assert not res.json()["resumed"]
    assert res.json()["attempt_number"] == 2


def test_max_attempts_block(api_client, setup_certification):
    """❌ Should block if student reached max attempts."""
    user, cert, q1, _ = setup_certification
    CertificationAttempt.objects.create(user=user, certification=cert, attempt_number=1, completed_at=timezone.now())
    CertificationAttempt.objects.create(user=user, certification=cert, attempt_number=2, completed_at=timezone.now())

    client = authenticate(api_client, user)
    res = client.post("/api/student/cert/attempts/start/", {"certification": cert.id})
    assert res.status_code == 400
    assert "Maximum" in res.json()["detail"]


def test_submit_pass(api_client, setup_certification):
    """✅ Submit answers and pass."""
    user, cert, q1, options = setup_certification
    attempt = CertificationAttempt.objects.create(user=user, certification=cert, attempt_number=1)
    client = authenticate(api_client, user)

    data = {"answers": [{"question": q1.id, "selected_options": [options[0].id]}]}
    res = client.post(f"/api/student/cert/attempts/{attempt.id}/submit/", data, format="json")
    assert res.status_code == 200
    assert res.json()["passed"] is True
    assert "certificate_url" in res.json()


def test_submit_fail_with_attempts_remaining(api_client, setup_certification):
    """❌ Fail and still have remaining attempts."""
    user, cert, q1, options = setup_certification
    attempt = CertificationAttempt.objects.create(user=user, certification=cert, attempt_number=1)
    client = authenticate(api_client, user)

    data = {"answers": [{"question": q1.id, "selected_options": [options[1].id]}]}
    res = client.post(f"/api/student/cert/attempts/{attempt.id}/submit/", data, format="json")
    assert res.status_code == 200
    assert res.json()["passed"] is False
    assert "attempt(s) remaining" in res.json()["message"]
