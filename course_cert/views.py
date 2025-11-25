from django.db import transaction
from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.utils import timezone
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from api.utils import StandardResponseMixin, CustomPagination
from .permissions import IsSuperUserOrStaff
from .models import (
    Certification,
    CertificationQuestion,
    CertificationAttempt,
    AttemptAnswer
)
from .serializers import (
    CertificationSerializer,
    CertificationPublicSerializer,
    CertificationQuestionSerializer,
    CertificationQuestionPublicSerializer,
    CertificationAttemptSerializer,
    AttemptAnswerSerializer
)
from courses.models import Enrollment
from .utils import generate_certificate_pdf


# -----------------------
# Admin ViewSets
# -----------------------

class CertificationAdminViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """Admin CRUD for Certifications with nested questions"""
    queryset = Certification.objects.prefetch_related("questions__options").all()
    serializer_class = CertificationSerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "course__title"]
    ordering_fields = ["created_at", "title"]
    pagination_class = CustomPagination
    
    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        """Get all attempts for a certification"""
        cert = self.get_object()
        attempts = CertificationAttempt.objects.filter(
            certification=cert
        ).select_related("user")

        data = [{
            "id": a.id,
            "user": a.user.username,
            "attempt_number": a.attempt_number,
            "score": a.score,
            "passed": a.passed,
            "started_at": a.started_at,
            "completed_at": a.completed_at,
        } for a in attempts]

        return Response(data)

    @action(detail=True, methods=["get"])
    def download_pdf(self, request, pk=None):
        """
        Download certificate as PDF with Z1 logo and college logo
        This endpoint generates a PDF using the backend PDF generation utility
        """
        cert = self.get_object()

        # Create a mock attempt object for PDF generation
        # In a real scenario, you might want to get an actual passed attempt
        try:
            # Try to get the first passed attempt for this certification
            attempt = CertificationAttempt.objects.filter(
                certification=cert,
                passed=True
            ).first()

            if not attempt:
                # If no passed attempt, create a mock one for preview
                attempt = cert.attempts.first()
                if not attempt:
                    return Response(
                        {"error": "No attempts found for this certification"},
                        status=status.HTTP_404_NOT_FOUND
                    )

            # Generate PDF using the utility function
            pdf_buffer = generate_certificate_pdf(attempt)

            # Return as file response
            response = HttpResponse(pdf_buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{cert.title}-Certificate.pdf"'
            return response

        except Exception as e:
            return Response(
                {"error": f"Error generating certificate PDF: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CertificationQuestionAdminViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """Admin CRUD for Questions (optional - can use nested in Certification)"""
    queryset = CertificationQuestion.objects.prefetch_related("options").all()
    serializer_class = CertificationQuestionSerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["text", "certification__title"]
    ordering_fields = ["order", "weight"]
    pagination_class = CustomPagination

    def get_queryset(self):
        qs = super().get_queryset()
        cert_id = self.request.query_params.get("certification")
        if cert_id:
            qs = qs.filter(certification_id=cert_id)
        return qs


# -----------------------
# Student ViewSets
# -----------------------

class StudentCertificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Students view certifications for their enrolled courses"""
    serializer_class = CertificationPublicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Certification.objects.filter(
            course__enrollments__student=user,
            is_active=True
        ).distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get questions for a certification (without showing correct answers)"""
        cert = self.get_object()
        
        # Verify enrollment
        if not Enrollment.objects.filter(
            student=request.user,
            course=cert.course
        ).exists():
            return Response(
                {"detail": "You must be enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        questions = CertificationQuestion.objects.filter(
            certification=cert,
            is_active=True
        ).prefetch_related("options").order_by("order")
        
        serializer = CertificationQuestionPublicSerializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def my_attempts(self, request, pk=None):
        """Get user's attempts for this certification"""
        cert = self.get_object()
        attempts = CertificationAttempt.objects.filter(
            user=request.user,
            certification=cert
        ).order_by("-attempt_number")
        
        serializer = CertificationAttemptSerializer(attempts, many=True)
        return Response(serializer.data)


class StudentCertificationAttemptViewSet(viewsets.ModelViewSet):
    """Students manage their certification attempts"""
    serializer_class = CertificationAttemptSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return CertificationAttempt.objects.filter(
            user=self.request.user
        ).select_related("certification")

    @action(detail=False, methods=["post"])
    def start(self, request):
        """
        Start or resume a certification attempt.
        Rules:
        - If student has an incomplete (not submitted/expired) attempt → resume it
        - Else if attempts < max_attempts → create new attempt
        - Else → reject
        """
        cert_id = request.data.get("certification")
        if not cert_id:
            return Response({"detail": "Certification ID required."}, status=status.HTTP_400_BAD_REQUEST)

        cert = get_object_or_404(Certification, id=cert_id, is_active=True)

        # Verify enrollment
        enrollment = Enrollment.objects.filter(student=request.user, course=cert.course).first()
        if not enrollment:
            return Response(
                {"detail": "You must be enrolled in this course."},
                status=status.HTTP_403_FORBIDDEN
            )
            # ✅ Enforce minimum progress threshold
        if enrollment.progress_percentage < 60:
            return Response(
                {"detail": f"You must complete at least 60% of the course to start this certification. "
                        f"Current progress: {enrollment.progress_percentage}%."},
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            # Check for existing incomplete attempt
            active_attempt = CertificationAttempt.objects.filter(
                user=request.user,
                certification=cert,
                completed_at__isnull=True
            ).order_by('-started_at').first()

            if active_attempt and not active_attempt.is_expired():
                # Resume existing attempt
                return Response({
                    "attempt_id": active_attempt.id,
                    "certification": cert.id,
                    "certification_title": cert.title,
                    "attempt_number": active_attempt.attempt_number,
                    "duration_minutes": cert.duration_minutes,
                    "started_at": active_attempt.started_at,
                    "expires_at": active_attempt.started_at + timezone.timedelta(
                        minutes=cert.duration_minutes
                    ),
                    "resumed": True
                }, status=status.HTTP_200_OK)

            # Count total attempts (completed and incomplete)
            total_attempts = CertificationAttempt.objects.filter(
                user=request.user,
                certification=cert
            ).count()

            if total_attempts >= cert.max_attempts:
                return Response(
                    {"detail": f"Maximum {cert.max_attempts} attempts reached. Cannot start a new attempt."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create a new attempt (explicitly set started_at for clarity)
            attempt_number = total_attempts + 1
            attempt = CertificationAttempt.objects.create(
                user=request.user,
                certification=cert,
                attempt_number=attempt_number,
                started_at=timezone.now(),
            )

        return Response({
            "attempt_id": attempt.id,
            "certification": cert.id,
            "certification_title": cert.title,
            "attempt_number": attempt.attempt_number,
            "duration_minutes": cert.duration_minutes,
            "started_at": attempt.started_at,
            "expires_at": attempt.started_at + timezone.timedelta(
                minutes=cert.duration_minutes
            ),
            "resumed": False
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """
        Submit answers for an attempt and auto-grade
        POST: {"answers": [{"question": <id>, "selected_options": [<id>, ...]}, ...]}
        """
        attempt = self.get_object()
        
        # Check if already completed
        if attempt.completed_at:
            return Response(
                {"detail": "This attempt has already been submitted."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if expired
        if attempt.is_expired():
            attempt.completed_at = timezone.now()
            attempt.score = 0
            attempt.passed = False
            attempt.save()
            return Response(
                {"detail": "This attempt has expired."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        answers_data = request.data.get("answers", [])
        
        if not answers_data:
            return Response(
                {"detail": "No answers provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate and save answers
        total_score = 0
        max_score = 0
        questions_answered = set()
        
        for ans_data in answers_data:
            question_id = ans_data.get("question")
            selected_options = ans_data.get("selected_options", [])
            
            if not question_id:
                continue
            
            try:
                question = CertificationQuestion.objects.prefetch_related(
                    "options"
                ).get(
                    id=question_id,
                    certification=attempt.certification,
                    is_active=True
                )
            except CertificationQuestion.DoesNotExist:
                continue
            
            # Validate answer
            ans_serializer = AttemptAnswerSerializer(data=ans_data)
            if not ans_serializer.is_valid():
                return Response(
                    ans_serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Save answer
            AttemptAnswer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={"selected_options": selected_options}
            )
            
            questions_answered.add(question_id)
            
            # Auto-grade
            correct_options = set(
                question.options.filter(is_correct=True).values_list("id", flat=True)
            )
            selected_set = set(selected_options)
            
            max_score += question.weight
            
            if question.is_multiple_correct:
                # All correct options must be selected, no incorrect ones
                if selected_set == correct_options:
                    total_score += question.weight
            else:
                # Single correct answer
                if len(selected_set) == 1 and selected_set.issubset(correct_options):
                    total_score += question.weight
        
        # Check if all questions were answered
        total_questions = CertificationQuestion.objects.filter(
            certification=attempt.certification,
            is_active=True
        ).count()
        
        if len(questions_answered) < total_questions:
            return Response(
                {
                    "detail": f"You must answer all {total_questions} questions. "
                              f"You answered {len(questions_answered)}."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate final score
        if max_score > 0:
            attempt.score = int((total_score / max_score) * 100)
        else:
            attempt.score = 0
        
        attempt.passed = attempt.score >= attempt.certification.passing_score
        attempt.completed_at = timezone.now()
        
        # Issue certificate if passed
        if attempt.passed:
            attempt.certificate_issued = True
            attempt.certificate_issued_at = timezone.now()
        
        attempt.save()
        
        # Prepare response
        result = {
            "attempt_id": attempt.id,
            "score": attempt.score,
            "passing_score": attempt.certification.passing_score,
            "passed": attempt.passed,
            "completed_at": attempt.completed_at,
            "total_questions": total_questions,
            "questions_answered": len(questions_answered)
        }
        
        if attempt.passed:
            result["certificate_url"] = request.build_absolute_uri(
                f"/api/certificates/{attempt.id}/download/"
            )
            result["message"] = "Congratulations! You passed the certification."
        else:
            remaining_attempts = (
                attempt.certification.max_attempts - attempt.attempt_number
            )
            if remaining_attempts > 0:
                result["message"] = (
                    f"You did not pass. You have {remaining_attempts} "
                    f"attempt(s) remaining."
                )
            else:
                result["message"] = (
                    "You did not pass and have no remaining attempts."
                )
        
        return Response(result)

    @action(detail=True, methods=["get"])
    def download_certificate(self, request, pk=None):
        """Download certificate PDF for a passed attempt"""
        try:
            attempt = self.get_object()

            if not attempt.passed:
                return Response(
                    {"detail": "Certificate not available. Attempt did not pass."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Generate PDF
            pdf_buffer = generate_certificate_pdf(attempt)

            # Ensure buffer is at the beginning
            if hasattr(pdf_buffer, 'seek'):
                pdf_buffer.seek(0)

            # Create filename
            filename = (
                f"certificate_{attempt.certification.title.replace(' ', '_')}_"
                f"{attempt.user.username}.pdf"
            )

            # Return FileResponse with proper headers to bypass DRF rendering
            response = FileResponse(
                pdf_buffer,
                content_type="application/pdf",
                as_attachment=True,
                filename=filename
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

            return response
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating certificate: {str(e)}", exc_info=True)
            return Response(
                {"detail": f"Error generating certificate: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Standalone view for certificate download that bypasses DRF rendering
@api_view(['GET'])
def download_certificate_view(request, attempt_id):
    """
    Standalone API view for downloading certificates.
    This bypasses DRF rendering to properly return PDF files.
    """
    try:
        # Get the attempt
        attempt = CertificationAttempt.objects.select_related(
            'user', 'certification'
        ).get(id=attempt_id, user=request.user)

        if not attempt.passed:
            return Response(
                {"detail": "Certificate not available. Attempt did not pass."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Generate PDF
        pdf_buffer = generate_certificate_pdf(attempt)

        # Ensure buffer is at the beginning
        if hasattr(pdf_buffer, 'seek'):
            pdf_buffer.seek(0)

        # Create filename
        filename = (
            f"certificate_{attempt.certification.title.replace(' ', '_')}_"
            f"{attempt.user.username}.pdf"
        )

        # Return FileResponse with proper headers
        response = FileResponse(
            pdf_buffer,
            content_type="application/pdf",
            as_attachment=True,
            filename=filename
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'

        return response
    except CertificationAttempt.DoesNotExist:
        return Response(
            {"detail": "Attempt not found or does not belong to you."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating certificate: {str(e)}", exc_info=True)
        return Response(
            {"detail": f"Error generating certificate: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
