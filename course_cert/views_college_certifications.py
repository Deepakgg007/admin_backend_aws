from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Certification, CertificationQuestion, CertificationOption
from .serializers import (
    CertificationSerializer,
    CertificationQuestionSerializer,
    CertificationOptionSerializer,
)
from .permissions import IsCollegeAuthenticated
from api.models import College
from courses.models import Course
from college.views import get_college_id_from_token


class CollegeCertificationViewSet(viewsets.ModelViewSet):
    """
    College-managed Certifications.
    A college can manage certifications only for its own published courses.
    """
    serializer_class = CertificationSerializer
    permission_classes = [IsCollegeAuthenticated]

    # ──────────────────────────────────────────────
    # Queryset Filtering
    # ──────────────────────────────────────────────
    def get_queryset(self):
        """Return certifications owned by the logged-in college."""
        college_id = get_college_id_from_token(self.request)
        return (
            Certification.objects.filter(college__college_id=college_id)
            .select_related("college", "course")
            .prefetch_related("questions__options")
            .order_by("-created_at")
        )

    # ──────────────────────────────────────────────
    # Create Certification
    # ──────────────────────────────────────────────
    def perform_create(self, serializer):
        """Attach certification to the logged-in college and validate course ownership."""
        college_id = get_college_id_from_token(self.request)
        college = get_object_or_404(College, college_id=college_id)

        course_id = self.request.data.get("course")
        if not course_id:
            raise ValueError("Course ID is required.")

        # Allow only this college's published courses
        course = get_object_or_404(
            Course, id=course_id, college=college, status="published"
        ).exclude(college__isnull=True)

        serializer.save(college=college, course=course)

    # ──────────────────────────────────────────────
    # Update Certification
    # ──────────────────────────────────────────────
    def perform_update(self, serializer):
        """Prevent cross-college or unpublished-course edits."""
        cert = self.get_object()
        college_id = get_college_id_from_token(self.request)

        if str(cert.college.college_id) != str(college_id):
            return Response(
                {"detail": "You do not have permission to edit this certification."},
                status=status.HTTP_403_FORBIDDEN,
            )

        course_id = self.request.data.get("course")
        if course_id:
            course = get_object_or_404(
                Course, id=course_id, college=cert.college, status="published"
            )
            serializer.save(course=course)
        else:
            serializer.save()

    # ──────────────────────────────────────────────
    # Manage Questions & Options
    # ──────────────────────────────────────────────
    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get all questions for a certification."""
        cert = self.get_object()
        questions = cert.questions.prefetch_related("options").order_by("order")
        serializer = CertificationQuestionSerializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def add_question(self, request, pk=None):
        """Add a new question."""
        cert = self.get_object()
        serializer = CertificationQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(certification=cert)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def add_option(self, request, pk=None):
        """Add an option to a question."""
        cert = self.get_object()
        question_id = request.data.get("question")
        question = get_object_or_404(CertificationQuestion, id=question_id, certification=cert)
        serializer = CertificationOptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(question=question)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"])
    def delete_question(self, request, pk=None):
        """Delete a question within college scope."""
        cert = self.get_object()
        qid = request.data.get("question_id")
        question = get_object_or_404(CertificationQuestion, id=qid, certification=cert)
        question.delete()
        return Response({"detail": "Question deleted."}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["delete"])
    def delete_option(self, request, pk=None):
        """Delete an option within college scope."""
        cert = self.get_object()
        oid = request.data.get("option_id")
        option = get_object_or_404(CertificationOption, id=oid, question__certification=cert)
        option.delete()
        return Response({"detail": "Option deleted."}, status=status.HTTP_204_NO_CONTENT)

    # ──────────────────────────────────────────────
    # Utility — List Available Courses
    # ──────────────────────────────────────────────
    @action(detail=False, methods=["get"])
    def available_courses(self, request):
        """
        List all published courses owned by this college.
        Used by frontend for certification creation dropdown.
        """
        college_id = get_college_id_from_token(request)
        college = get_object_or_404(College, college_id=college_id)

        courses = Course.objects.filter(
            college=college, status="published"
        ).values("id", "title", "difficulty_level", "duration_hours")

        return Response(list(courses))
