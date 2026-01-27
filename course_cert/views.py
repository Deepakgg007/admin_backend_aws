from django.db import transaction, models
from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.utils import timezone
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django_filters.rest_framework import DjangoFilterBackend
import json
import requests
from decouple import config

from api.utils import StandardResponseMixin, CustomPagination
from .permissions import IsSuperUserOrStaff
from .models import (
    Certification,
    CertificationQuestion,
    CertificationQuestionBank,
    CertificationAttempt,
    AttemptAnswer,
    AttemptAnswerBank,
    QuestionBank,
    QuestionBankOption,
    QuestionBankCategory,
    AIGenerationLog,
    AIProviderSettings
)
from .serializers import (
    CertificationSerializer,
    CertificationPublicSerializer,
    CertificationQuestionSerializer,
    CertificationQuestionPublicSerializer,
    CertificationQuestionBankSerializer,
    CertificationAttemptSerializer,
    AttemptAnswerSerializer,
    QuestionBankSerializer,
    QuestionBankListSerializer,
    QuestionBankCategorySerializer,
    AIGenerationLogSerializer,
    AIProviderSettingsSerializer,
    AIProviderSettingsListSerializer,
    AIGenerateQuestionsSerializer,
    ImportToCertificationSerializer
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
        ).select_related("course__college").distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get questions for a certification (without showing correct answers)"""
        from course_cert.serializers import CertificationQuestionBankPublicSerializer
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

        # Get manual questions
        manual_questions = CertificationQuestion.objects.filter(
            certification=cert,
            is_active=True
        ).prefetch_related("options").order_by("order")

        # Get bank questions
        bank_questions = CertificationQuestionBank.objects.filter(
            certification=cert,
            is_active=True
        ).select_related("question").prefetch_related("question__options").order_by("order")

        # Serialize both types
        manual_serializer = CertificationQuestionPublicSerializer(manual_questions, many=True)
        bank_serializer = CertificationQuestionBankPublicSerializer(bank_questions, many=True)

        # Combine and return
        all_questions = []

        # Mark question type for frontend
        for q in manual_serializer.data:
            q['question_type'] = 'manual'
            all_questions.append(q)

        for q in bank_serializer.data:
            q['question_type'] = 'bank'
            # Map bank question fields to match manual question structure
            q['text'] = q.pop('question_text')
            all_questions.append(q)

        # Sort by order
        all_questions.sort(key=lambda x: x['order'])

        return Response(all_questions)

    @action(detail=True, methods=["get"])
    def my_attempts(self, request, pk=None):
        """Get user's attempts for this certification"""
        cert = self.get_object()
        attempts = CertificationAttempt.objects.filter(
            user=request.user,
            certification=cert
        ).select_related("certification__course__college", "user__college").order_by("-attempt_number")

        serializer = CertificationAttemptSerializer(
            attempts,
            many=True,
            context={"request": request}
        )
        return Response(serializer.data)


class StudentCertificationAttemptViewSet(viewsets.ModelViewSet):
    """Students manage their certification attempts"""
    serializer_class = CertificationAttemptSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return CertificationAttempt.objects.filter(
            user=self.request.user
        ).select_related("certification__course__college", "user__college")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

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
        Handles both manual questions and Question Bank questions
        POST: {"answers": [{"question": <id>, "selected_options": [<id>, ...], "question_type": "manual|bank"}, ...]}
        """
        from course_cert.serializers import AttemptAnswerBankSerializer
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
        manual_questions_answered = set()
        bank_questions_answered = set()

        for ans_data in answers_data:
            question_id = ans_data.get("question")
            selected_options = ans_data.get("selected_options", [])
            question_type = ans_data.get("question_type", "manual")  # Default to manual for backward compatibility

            if not question_id:
                continue

            if question_type == "manual":
                # Handle manual questions (old system)
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
                ans_serializer = AttemptAnswerSerializer(data={"question": question_id, "selected_options": selected_options})
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

                manual_questions_answered.add(question_id)

                # Auto-grade
                correct_options = set(
                    question.options.filter(is_correct=True).values_list("id", flat=True)
                )
                selected_set = set(selected_options)

                max_score += question.weight

                if question.is_multiple_correct:
                    if selected_set == correct_options:
                        total_score += question.weight
                else:
                    if len(selected_set) == 1 and selected_set.issubset(correct_options):
                        total_score += question.weight

            elif question_type == "bank":
                # Handle Question Bank questions (new system)
                try:
                    cert_question = CertificationQuestionBank.objects.select_related(
                        "question"
                    ).prefetch_related(
                        "question__options"
                    ).get(
                        id=question_id,
                        certification=attempt.certification,
                        is_active=True
                    )
                except CertificationQuestionBank.DoesNotExist:
                    continue

                # Validate answer
                ans_serializer = AttemptAnswerBankSerializer(data={"cert_question": question_id, "selected_options": selected_options})
                if not ans_serializer.is_valid():
                    return Response(
                        ans_serializer.errors,
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Save answer
                AttemptAnswerBank.objects.update_or_create(
                    attempt=attempt,
                    cert_question=cert_question,
                    defaults={"selected_options": selected_options}
                )

                bank_questions_answered.add(question_id)

                # Auto-grade
                question = cert_question.question
                correct_options = set(
                    question.options.filter(is_correct=True).values_list("id", flat=True)
                )
                selected_set = set(selected_options)

                max_score += cert_question.weight

                if question.is_multiple_correct:
                    if selected_set == correct_options:
                        total_score += cert_question.weight
                else:
                    if len(selected_set) == 1 and selected_set.issubset(correct_options):
                        total_score += cert_question.weight

        # Check if all questions were answered
        total_manual_questions = CertificationQuestion.objects.filter(
            certification=attempt.certification,
            is_active=True
        ).count()

        total_bank_questions = CertificationQuestionBank.objects.filter(
            certification=attempt.certification,
            is_active=True
        ).count()

        total_questions = total_manual_questions + total_bank_questions

        if len(manual_questions_answered) < total_manual_questions or len(bank_questions_answered) < total_bank_questions:
            return Response(
                {
                    "detail": f"You must answer all {total_questions} questions. "
                              f"You answered {len(manual_questions_answered) + len(bank_questions_answered)}."
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
            "questions_answered": len(manual_questions_answered) + len(bank_questions_answered)
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
# This file contains the ViewSets for Question Bank feature
# To be appended to views.py

# ====================================
# QUESTION BANK VIEWSETS
# ====================================

class QuestionBankCategoryViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """CRUD for Question Bank Categories"""
    queryset = QuestionBankCategory.objects.all()
    serializer_class = QuestionBankCategorySerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs


class QuestionBankViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """CRUD for Question Bank Items with AI generation"""
    queryset = QuestionBank.objects.prefetch_related('options').select_related('category', 'course')
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['text', 'tags']
    ordering_fields = ['created_at', 'difficulty', 'weight']
    filterset_fields = ['difficulty', 'category', 'course', 'source', 'is_active']
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return QuestionBankListSerializer
        return QuestionBankSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        tags = self.request.query_params.get('tags')
        if tags:
            tag_list = [t.strip() for t in tags.split(',')]
            for tag in tag_list:
                qs = qs.filter(tags__contains=[tag])

        return qs

    @action(detail=False, methods=['post'])
    def generate_with_ai(self, request):
        """Generate questions using AI (OpenRouter, Gemini, Z.AI)"""
        serializer = AIGenerateQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        topic = data['topic']
        difficulty = data['difficulty']
        num_questions = data['num_questions']
        category = data.get('category')
        course_id = data.get('course')
        tags = data.get('tags', [])
        additional_context = data.get('additional_context', '')

        course = None
        if course_id:
            from courses.models import Course
            course = Course.objects.filter(id=course_id).first()

        # Get AI provider settings from database or fallback to environment
        provider_settings = AIProviderSettings.get_default_provider()

        # If no default provider, try to get any active provider
        if not provider_settings:
            active_providers = AIProviderSettings.get_active_providers()
            if active_providers.exists():
                provider_settings = active_providers.first()

        if provider_settings:
            api_key = provider_settings.api_key
            provider_type = provider_settings.provider
            model = provider_settings.default_model or 'openai/gpt-4o-mini'
            temperature = provider_settings.temperature
            max_tokens = provider_settings.max_tokens
            api_endpoint = provider_settings.api_endpoint
        else:
            # Fallback to environment variable for backward compatibility
            api_key = config('OPENROUTER_API_KEY', default='')
            provider_type = 'OPENROUTER'
            model = 'openai/gpt-4o-mini'
            temperature = 0.7
            max_tokens = 4000
            api_endpoint = None

        if not api_key:
            return Response(
                {'error': 'No AI provider configured. Please configure an AI provider in AI Settings or set OPENROUTER_API_KEY in environment.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        prompt = self._build_generation_prompt(topic, difficulty, num_questions, additional_context)

        log = AIGenerationLog.objects.create(
            prompt=prompt,
            topic=topic,
            difficulty=difficulty,
            num_questions=num_questions,
            model_used=model,
            provider=provider_type,
            status='PENDING',
            created_by=request.user
        )

        try:
            # Call the appropriate AI provider
            if provider_type == 'OPENROUTER':
                response = requests.post(
                    api_endpoint or 'https://openrouter.ai/api/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json',
                        'HTTP-Referer': 'https://educational-platform.com',
                        'X-Title': 'Educational Platform Question Generator'
                    },
                    json={
                        'model': model,
                        'messages': [
                            {
                                'role': 'system',
                                'content': 'You are an expert educational content creator. Generate high-quality multiple choice questions in valid JSON format only. Do not include any text outside the JSON.'
                            },
                            {
                                'role': 'user',
                                'content': prompt
                            }
                        ],
                        'temperature': temperature,
                        'max_tokens': max_tokens
                    },
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                ai_content = result['choices'][0]['message']['content']

            elif provider_type == 'GEMINI':
                endpoint = api_endpoint or f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
                response = requests.post(
                    f'{endpoint}?key={api_key}',
                    headers={'Content-Type': 'application/json'},
                    json={
                        'contents': [{
                            'parts': [{
                                'text': f'You are an expert educational content creator. Generate high-quality multiple choice questions in valid JSON format only. Do not include any text outside the JSON.\n\n{prompt}'
                            }]
                        }],
                        'generationConfig': {
                            'temperature': temperature,
                            'maxOutputTokens': max_tokens
                        }
                    },
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                ai_content = result['candidates'][0]['content']['parts'][0]['text']

            elif provider_type == 'ZAI':
                endpoint = api_endpoint or 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
                if not endpoint.endswith('/chat/completions'):
                    endpoint = endpoint.rstrip('/') + '/chat/completions'

                response = requests.post(
                    endpoint,
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': model,
                        'messages': [
                            {
                                'role': 'system',
                                'content': 'You are an expert educational content creator. Generate high-quality multiple choice questions in valid JSON format only. Do not include any text outside the JSON.'
                            },
                            {
                                'role': 'user',
                                'content': prompt
                            }
                        ],
                        'temperature': temperature,
                        'max_tokens': max_tokens
                    },
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                ai_content = result['choices'][0]['message']['content']
            else:
                return Response(
                    {'error': f'Unsupported AI provider: {provider_type}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            log.response_raw = ai_content

            questions_data = self._parse_ai_response(ai_content)

            created_questions = []
            with transaction.atomic():
                for q_data in questions_data:
                    question = QuestionBank.objects.create(
                        text=q_data['question'],
                        explanation=q_data.get('explanation', ''),
                        is_multiple_correct=q_data.get('is_multiple_correct', False),
                        difficulty=difficulty,
                        category=category,
                        course=course,
                        tags=tags + [topic.lower()],
                        source='AI_GENERATED',
                        ai_prompt=prompt,
                        ai_model=model,
                        weight=1,
                        is_active=True,
                        created_by=request.user
                    )

                    for idx, opt_data in enumerate(q_data['options']):
                        QuestionBankOption.objects.create(
                            question=question,
                            text=opt_data['text'],
                            is_correct=opt_data['is_correct'],
                            order=idx
                        )

                    created_questions.append(question)

            log.status = 'SUCCESS'
            log.questions_created = len(created_questions)
            log.completed_at = timezone.now()
            log.save()

            return Response({
                'success': True,
                'message': f'Successfully generated {len(created_questions)} questions.',
                'questions': QuestionBankSerializer(created_questions, many=True).data,
                'log_id': log.id
            }, status=status.HTTP_201_CREATED)

        except requests.exceptions.RequestException as e:
            log.status = 'FAILED'
            log.error_message = f'API request failed: {str(e)}'
            log.completed_at = timezone.now()
            log.save()

            return Response(
                {'error': f'Failed to connect to AI service: {str(e)}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.status = 'FAILED'
            log.error_message = f'Failed to parse AI response: {str(e)}'
            log.completed_at = timezone.now()
            log.save()

            return Response(
                {'error': f'Failed to parse AI response: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _build_generation_prompt(self, topic, difficulty, num_questions, additional_context=''):
        """Build the prompt for AI question generation"""
        difficulty_desc = {
            'EASY': 'basic understanding and recall',
            'MEDIUM': 'application and analysis',
            'HARD': 'advanced analysis, synthesis, and evaluation'
        }

        prompt = f"""Generate exactly {num_questions} multiple choice questions about "{topic}".

Difficulty Level: {difficulty} - Questions should test {difficulty_desc.get(difficulty, 'understanding')}.

Requirements:
1. Each question must have exactly 4 options (A, B, C, D)
2. Exactly one option should be correct (unless specified otherwise)
3. Options should be plausible and educational
4. Include a brief explanation for the correct answer
5. Questions should be clear and unambiguous

{f'Additional context: {additional_context}' if additional_context else ''}

Return ONLY a valid JSON array with this exact structure (no other text):
[
  {{
    "question": "The question text here?",
    "options": [
      {{"text": "Option A text", "is_correct": false}},
      {{"text": "Option B text", "is_correct": true}},
      {{"text": "Option C text", "is_correct": false}},
      {{"text": "Option D text", "is_correct": false}}
    ],
    "explanation": "Brief explanation of why the correct answer is correct.",
    "is_multiple_correct": false
  }}
]"""
        return prompt

    def _parse_ai_response(self, content):
        """Parse the AI response and extract questions"""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]

        content = content.strip()

        questions = json.loads(content)

        if not isinstance(questions, list):
            raise ValueError("Expected a list of questions")

        validated_questions = []
        for q in questions:
            if 'question' not in q or 'options' not in q:
                continue

            if len(q['options']) < 2:
                continue

            # Ensure at least one correct answer
            has_correct = any(opt.get('is_correct', False) for opt in q['options'])
            if not has_correct:
                q['options'][0]['is_correct'] = True

            validated_questions.append(q)

        return validated_questions

    @action(detail=False, methods=['post'])
    def import_to_certification(self, request):
        """Import questions from bank to a certification using Question Bank links"""
        serializer = ImportToCertificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question_ids = serializer.validated_data['question_ids']
        certification_id = serializer.validated_data['certification_id']

        from course_cert.models import Certification, CertificationQuestionBank

        try:
            certification = Certification.objects.get(id=certification_id)
        except Certification.DoesNotExist:
            return Response(
                {'error': 'Certification not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        bank_questions = QuestionBank.objects.filter(id__in=question_ids, is_active=True).prefetch_related('options')

        if not bank_questions.exists():
            return Response(
                {'error': 'No valid questions found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get max order from both manual questions and bank questions
        manual_max = certification.questions.aggregate(max_order=models.Max('order'))['max_order'] or 0
        bank_max = certification.bank_questions.aggregate(max_order=models.Max('order'))['max_order'] or 0
        max_order = max(manual_max, bank_max)

        created_links = []
        with transaction.atomic():
            for idx, bank_q in enumerate(bank_questions):
                # Check if question is already linked
                if not CertificationQuestionBank.objects.filter(
                    certification=certification,
                    question=bank_q
                ).exists():
                    link = CertificationQuestionBank.objects.create(
                        certification=certification,
                        question=bank_q,
                        weight=bank_q.weight,
                        order=max_order + idx + 1,
                        is_active=True
                    )
                    created_links.append(link)

        return Response({
            'success': True,
            'message': f'Successfully imported {len(created_links)} questions to certification.',
            'certification_id': certification_id,
            'questions_imported': len(created_links)
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get question bank statistics"""
        total = QuestionBank.objects.count()
        active = QuestionBank.objects.filter(is_active=True).count()

        by_difficulty = {}
        for choice in QuestionBank.DIFFICULTY_CHOICES:
            by_difficulty[choice[0]] = QuestionBank.objects.filter(
                difficulty=choice[0], is_active=True
            ).count()

        by_source = {}
        for choice in QuestionBank.SOURCE_CHOICES:
            by_source[choice[0]] = QuestionBank.objects.filter(
                source=choice[0], is_active=True
            ).count()

        by_category = list(
            QuestionBankCategory.objects.filter(is_active=True).values('id', 'name').annotate(
                count=models.Count('questions', filter=models.Q(questions__is_active=True))
            )
        )

        return Response({
            'total_questions': total,
            'active_questions': active,
            'by_difficulty': by_difficulty,
            'by_source': by_source,
            'by_category': by_category
        })


class CertificationQuestionBankViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """CRUD for Certification Question Bank Links"""
    queryset = CertificationQuestionBank.objects.select_related('certification', 'question').all()
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    serializer_class = CertificationQuestionBankSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['certification', 'question', 'is_active']
    ordering_fields = ['order', 'added_at']

    def perform_destroy(self, instance):
        """Delete a question from certification (soft delete by setting is_active=False)"""
        instance.is_active = False
        instance.save()


class AIProviderSettingsViewSet(viewsets.ModelViewSet, StandardResponseMixin):
    """CRUD for AI Provider Settings"""
    queryset = AIProviderSettings.objects.all()
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['provider', 'updated_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return AIProviderSettingsListSerializer
        return AIProviderSettingsSerializer

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a provider as the default"""
        provider = self.get_object()

        if not provider.is_active:
            return Response(
                {'error': 'Cannot set an inactive provider as default. Please activate it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not provider.api_key:
            return Response(
                {'error': 'Cannot set a provider without an API key as default.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Unset other defaults and set this one
        AIProviderSettings.objects.exclude(pk=pk).update(is_default=False)
        provider.is_default = True
        provider.save()

        return Response({
            'success': True,
            'message': f'{provider.get_provider_display()} is now the default AI provider.'
        })

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test the API connection for a provider"""
        provider = self.get_object()

        if not provider.api_key:
            return Response(
                {'error': 'No API key configured for this provider.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if provider.provider == 'OPENROUTER':
                response = requests.post(
                    provider.api_endpoint or 'https://openrouter.ai/api/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {provider.api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': provider.default_model or 'openai/gpt-4o-mini',
                        'messages': [{'role': 'user', 'content': 'Hello'}],
                        'max_tokens': 5
                    },
                    timeout=10
                )
                response.raise_for_status()

            elif provider.provider == 'GEMINI':
                endpoint = provider.api_endpoint or f'https://generativelanguage.googleapis.com/v1beta/models/{provider.default_model or "gemini-pro"}:generateContent'
                response = requests.post(
                    f'{endpoint}?key={provider.api_key}',
                    headers={'Content-Type': 'application/json'},
                    json={
                        'contents': [{'parts': [{'text': 'Hello'}]}]
                    },
                    timeout=10
                )
                response.raise_for_status()

            elif provider.provider == 'ZAI':
                endpoint = provider.api_endpoint or 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
                response = requests.post(
                    endpoint,
                    headers={
                        'Authorization': f'Bearer {provider.api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': provider.default_model or 'glm-4',
                        'messages': [{'role': 'user', 'content': 'Hello'}],
                        'max_tokens': 5
                    },
                    timeout=10
                )
                response.raise_for_status()

            return Response({
                'success': True,
                'message': f'Successfully connected to {provider.get_provider_display()}.'
            })

        except requests.exceptions.RequestException as e:
            return Response({
                'success': False,
                'error': f'Connection failed: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def available_providers(self, request):
        """Get list of available provider choices"""
        return Response({
            'providers': [
                {'value': choice[0], 'label': choice[1]}
                for choice in AIProviderSettings.PROVIDER_CHOICES
            ],
            'default_models': {
                'OPENROUTER': ['openai/gpt-4o', 'openai/gpt-4o-mini', 'anthropic/claude-3.5-sonnet', 'anthropic/claude-3-haiku', 'google/gemini-2.0-flash-exp', 'meta-llama/llama-3.1-70b-instruct'],
                'GEMINI': ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
                'ZAI': ['glm-4.7', 'glm-4.6', 'glm-4.5', 'glm-4.5-air', 'glm-4.5-flash', 'glm-4.6v', 'glm-4.5v']
            },
            'default_endpoints': {
                'OPENROUTER': 'https://openrouter.ai/api/v1/chat/completions',
                'GEMINI': 'https://generativelanguage.googleapis.com/v1beta/models',
                'ZAI': 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
            }
        })

    @action(detail=False, methods=['get'])
    def active_provider(self, request):
        """Get the currently active default provider"""
        provider = AIProviderSettings.get_default_provider()
        if provider:
            return Response({
                'has_active_provider': True,
                'provider': AIProviderSettingsListSerializer(provider).data
            })
        return Response({
            'has_active_provider': False,
            'provider': None,
            'message': 'No active default AI provider configured.'
        })


class AIGenerationLogViewSet(viewsets.ReadOnlyModelViewSet, StandardResponseMixin):
    """View AI generation logs"""
    queryset = AIGenerationLog.objects.all()
    serializer_class = AIGenerationLogSerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrStaff]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = ['created_at']
    filterset_fields = ['status', 'difficulty']
    pagination_class = CustomPagination
