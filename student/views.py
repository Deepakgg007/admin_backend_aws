from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Max
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import CodingChallengeSubmission, CompanyChallengeSubmission, StudentChallengeSubmission
from .serializers import (
    StudentChallengeSubmissionSerializer,
    StudentChallengeSubmissionCreateSerializer,
    StudentChallengeSubmissionListSerializer
)
from coding.models import Challenge
from .code_executor import _run_code_in_sandbox

class StudentChallengeSubmissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student challenge submissions
    Students can view their own submissions and create new ones
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return submissions for the current user only"""
        user = self.request.user
        queryset = StudentChallengeSubmission.objects.filter(user=user)

        # Filter by challenge if provided
        challenge_slug = self.request.query_params.get('challenge', None)
        if challenge_slug:
            queryset = queryset.filter(challenge__slug=challenge_slug)

        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related('challenge', 'user')

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return StudentChallengeSubmissionCreateSerializer
        elif self.action == 'list':
            return StudentChallengeSubmissionListSerializer
        return StudentChallengeSubmissionSerializer

    def create(self, request, *args, **kwargs):
        """Create new submission"""
        user = request.user

        # Check if user is approved
        if user.approval_status != 'approved':
            return Response(
                {'error': 'Your account must be approved before submitting challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user is verified
        if not user.is_verified:
            return Response(
                {'error': 'Your account is not verified yet. Please verify your account to submit challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if college is active
        if user.college and not user.college.is_active:
            return Response(
                {'error': 'Your college is currently inactive. Please contact support for more information.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # TODO: Integrate with code execution engine to evaluate submission
        # For now, we'll just save it as PENDING
        submission = serializer.save(user=request.user)

        # Return full submission details
        response_serializer = StudentChallengeSubmissionSerializer(submission)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def my_submissions(self, request):
        """Get all submissions for current user"""
        submissions = self.get_queryset()
        serializer = StudentChallengeSubmissionListSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get submission statistics for current user"""
        user = request.user
        submissions = StudentChallengeSubmission.objects.filter(user=user)

        stats = {
            'total_submissions': submissions.count(),
            'accepted': submissions.filter(status='ACCEPTED').count(),
            'wrong_answer': submissions.filter(status='WRONG_ANSWER').count(),
            'runtime_error': submissions.filter(status='RUNTIME_ERROR').count(),
            'compilation_error': submissions.filter(status='COMPILATION_ERROR').count(),
            'time_limit_exceeded': submissions.filter(status='TIME_LIMIT_EXCEEDED').count(),
            'problems_solved': submissions.filter(status='ACCEPTED', is_best_submission=True).values('challenge').distinct().count(),
            'total_score': sum(submissions.filter(is_best_submission=True).values_list('score', flat=True)),
            'average_score': submissions.filter(status='ACCEPTED').aggregate(Max('score'))['score__max'] or 0,
        }

        return Response(stats)

    @action(detail=False, methods=['get'], url_path='by-challenge/(?P<challenge_slug>[^/.]+)')
    def by_challenge(self, request, challenge_slug=None):
        """Get all submissions for a specific challenge"""
        submissions = self.get_queryset().filter(challenge__slug=challenge_slug)
        serializer = StudentChallengeSubmissionSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent submissions (last 10)"""
        submissions = self.get_queryset()[:10]
        serializer = StudentChallengeSubmissionListSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='submit')
    def submit_code(self, request):
        """Execute code against all test cases and create submission"""
        user = request.user

        # Check if user is approved
        if user.approval_status != 'approved':
            return Response(
                {'error': 'Your account must be approved before submitting challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user is verified
        if not user.is_verified:
            return Response(
                {'error': 'Your account is not verified yet. Please verify your account to submit challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if college is active
        if user.college and not user.college.is_active:
            return Response(
                {'error': 'Your college is currently inactive. Please contact support for more information.'},
                status=status.HTTP_403_FORBIDDEN
            )

        challenge_slug = request.data.get('challenge_slug')
        user_code = request.data.get('code')
        language = request.data.get('language', 'python')

        # Get company/concept info if this is a company challenge
        company_id = request.data.get('company_id')
        company_name = request.data.get('company_name', '')
        concept_id = request.data.get('concept_id')
        concept_name = request.data.get('concept_name', '')

        if not challenge_slug or not user_code:
            return Response(
                {'error': 'challenge_slug and code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        challenge = get_object_or_404(Challenge, slug=challenge_slug)
        test_cases = challenge.test_cases.all().order_by('is_sample', 'pk')

        if not test_cases.exists():
            return Response(
                {'error': 'No test cases found for this challenge'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = []
        passed_tests = 0

        for test_case in test_cases:
            result = _run_code_in_sandbox(
                code=user_code,
                input_data=test_case.input_data,
                language=language,
                challenge=challenge
            )

            user_output = result['output'].strip()
            expected = test_case.expected_output.strip()
            is_correct = (user_output == expected)

            if is_correct:
                passed_tests += 1

            results.append({
                'input': test_case.input_data if not test_case.hidden else '[Hidden]',
                'expected': expected if not test_case.hidden else '[Hidden]',
                'user_output': user_output if not test_case.hidden else '[Hidden]',
                'is_correct': is_correct,
                'is_sample': test_case.is_sample,
                'hidden': test_case.hidden,
                'runtime': result['runtime'],
                'memory': result['memory'],
                'error': result['error'],
                'status': result['status'],
            })

        # Determine final status
        if passed_tests == len(test_cases):
            final_status = 'ACCEPTED'
        elif any(r['status'] == 'COMPILATION_ERROR' for r in results):
            final_status = 'COMPILATION_ERROR'
        elif any(r['status'] == 'TIME_LIMIT_EXCEEDED' for r in results):
            final_status = 'TIME_LIMIT_EXCEEDED'
        elif any(r['status'] == 'RUNTIME_ERROR' for r in results):
            final_status = 'RUNTIME_ERROR'
        elif any(r['status'] == 'SYSTEM_ERROR' for r in results):
            final_status = 'SYSTEM_ERROR'
        else:
            final_status = 'WRONG_ANSWER'

        score = int((passed_tests / len(test_cases)) * challenge.max_score) if test_cases else 0

        # Calculate runtime and memory (average of all tests)
        avg_runtime = sum(r['runtime'] for r in results) / len(results) if results else 0
        avg_memory = sum(r['memory'] for r in results) / len(results) if results else 0

        # Determine if this is a company challenge or coding challenge
        is_company_challenge = company_id is not None and concept_id is not None

        if is_company_challenge:
            # Create company challenge submission
            submission = CompanyChallengeSubmission.objects.create(
                user=request.user,
                company_id=company_id,
                company_name=company_name,
                concept_id=concept_id,
                concept_name=concept_name,
                challenge_id=challenge.id,
                challenge_slug=challenge.slug,
                challenge_title=challenge.title,
                submitted_code=user_code,
                language=language,
                status=final_status,
                passed_tests=passed_tests,
                total_tests=len(test_cases),
                score=score,
                runtime=avg_runtime,
                memory_used=avg_memory,
                test_results=results,
            )
        else:
            # Create regular coding challenge submission
            submission = CodingChallengeSubmission.objects.create(
                user=request.user,
                challenge=challenge,
                submitted_code=user_code,
                language=language,
                status=final_status,
                passed_tests=passed_tests,
                total_tests=len(test_cases),
                score=score,
                runtime=avg_runtime,
                memory_used=avg_memory,
                test_results=results,
            )

        return Response({
            'success': True,
            'submission_id': submission.id,
            'status': final_status,
            'passed_tests': passed_tests,
            'total_tests': len(test_cases),
            'score': score,
            'runtime': avg_runtime,
            'memory': avg_memory,
            'results': results,
            'submission_type': 'company' if is_company_challenge else 'coding',
        })

    @action(detail=False, methods=['post'], url_path='run')
    def run_code(self, request):
        """Run code with custom input OR sample test cases (no submission created)"""
        user_code = request.data.get('code')
        custom_input = request.data.get('input', '').strip()
        language = request.data.get('language', 'python')
        challenge_slug = request.data.get('challenge_slug')

        if not user_code:
            return Response(
                {'error': 'code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # If custom input is provided, use it
        if custom_input:
            result = _run_code_in_sandbox(
                code=user_code,
                input_data=custom_input,
                language=language,
                challenge=None
            )

            return Response({
                'success': True,
                'output': result['output'],
                'error': result['error'],
                'runtime': result['runtime'],
                'memory': result['memory'],
                'status': result['status'],
            })

        # Otherwise, use sample test cases from challenge
        if not challenge_slug:
            return Response(
                {'error': 'Either provide custom input or challenge_slug'},
                status=status.HTTP_400_BAD_REQUEST
            )

        challenge = get_object_or_404(Challenge, slug=challenge_slug)

        # Get sample test cases - includes both visible and hidden ones
        # Hidden ones will run but won't show input/output to user
        test_cases = challenge.test_cases.filter(is_sample=True)

        if not test_cases.exists():
            return Response(
                {'error': 'No sample test cases available for this challenge'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = []
        for test_case in test_cases:
            result = _run_code_in_sandbox(
                code=user_code,
                input_data=test_case.input_data,
                language=language,
                challenge=challenge
            )

            user_output = result['output'].strip()
            expected = test_case.expected_output.strip()
            is_correct = (user_output == expected)

            # Hide input/output for hidden test cases (like HackerRank)
            results.append({
                'input': '[Hidden]' if test_case.hidden else test_case.input_data,
                'expected': '[Hidden]' if test_case.hidden else expected,
                'output': '[Hidden]' if test_case.hidden else result['output'],
                'error': result['error'] if not test_case.hidden else '',
                'is_correct': is_correct,
                'is_sample': test_case.is_sample,
                'hidden': test_case.hidden,
                'runtime': result['runtime'],
                'memory': result['memory'],
                'status': result['status'],
            })

        return Response({
            'success': True,
            'results': results,
        })

    @action(detail=False, methods=['get'], url_path='last-code/(?P<challenge_slug>[^/.]+)')
    def get_last_code(self, request, challenge_slug=None):
        """
        Get user's last submission code for a challenge
        GET /api/student/submissions/last-code/{challenge_slug}/?language=python&company_id=1&concept_id=2
        """
        if not challenge_slug:
            return Response(
                {'error': 'challenge_slug is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        language = request.query_params.get('language', 'python')
        company_id = request.query_params.get('company_id')
        concept_id = request.query_params.get('concept_id')

        # Determine if this is a company challenge or coding challenge
        is_company_challenge = company_id is not None and concept_id is not None

        try:
            if is_company_challenge:
                # Get last company challenge submission
                last_submission = CompanyChallengeSubmission.objects.filter(
                    user=request.user,
                    challenge_slug=challenge_slug,
                    company_id=int(company_id),
                    concept_id=int(concept_id),
                    language=language
                ).order_by('-submitted_at').first()
            else:
                # Get last coding challenge submission
                challenge = get_object_or_404(Challenge, slug=challenge_slug)
                last_submission = CodingChallengeSubmission.objects.filter(
                    user=request.user,
                    challenge=challenge,
                    language=language
                ).order_by('-submitted_at').first()

            if last_submission:
                return Response({
                    'success': True,
                    'has_code': True,
                    'code': last_submission.submitted_code,
                    'language': last_submission.language,
                    'status': last_submission.status,
                    'score': last_submission.score,
                    'submitted_at': last_submission.submitted_at,
                })
            else:
                return Response({
                    'success': True,
                    'has_code': False,
                    'code': None,
                })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# ==================== Content Submission Views ====================
# Handles MCQ, coding, document, and video submissions (NO page submissions)

from courses.models import (
    Task, TaskQuestion, TaskMCQ, TaskCoding, TaskDocument,
    TaskVideo, Enrollment, TaskSubmission
)
from .models import ContentSubmission
from .serializers import (
    MCQSubmissionSerializer, CodingSubmissionSerializer,
    ContentCompletionSerializer, MCQSubmissionResponseSerializer,
    ContentSubmissionSerializer
)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_mcq_question(request, task_id):
    """
    Submit MCQ question answer
    POST /api/student/tasks/{task_id}/submit-mcq/
    Body: {"question_id": 123, "selected_choice": 2}
    """
    task = get_object_or_404(Task, id=task_id)

    # Check enrollment
    if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
        return Response({
            'success': False,
            'message': 'You are not enrolled in this course'
        }, status=status.HTTP_403_FORBIDDEN)

    # Validate input
    serializer = MCQSubmissionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid submission data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    question_id = serializer.validated_data['question_id']
    selected_choice = serializer.validated_data['selected_choice']

    question = get_object_or_404(TaskQuestion, id=question_id, task=task)

    if question.question_type != 'mcq':
        return Response({
            'success': False,
            'message': 'Question is not an MCQ'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        mcq_details = question.mcq_details
    except TaskMCQ.DoesNotExist:
        return Response({
            'success': False,
            'message': 'MCQ details not found'
        }, status=status.HTTP_404_NOT_FOUND)

    # Check correctness
    choice_correctness = {
        1: mcq_details.choice_1_is_correct,
        2: mcq_details.choice_2_is_correct,
        3: mcq_details.choice_3_is_correct,
        4: mcq_details.choice_4_is_correct,
    }

    is_correct = choice_correctness.get(selected_choice, False)
    score = question.marks if is_correct else 0

    # Find all correct choices for response
    correct_choices = [i for i in range(1, 5) if choice_correctness.get(i, False)]

    try:
        with transaction.atomic():
            # Create or update submission
            submission, created = ContentSubmission.objects.update_or_create(
                student=request.user,
                question=question,
                defaults={
                    'task': task,
                    'submission_type': 'question',
                    'mcq_selected_choice': selected_choice,
                    'answer_text': str(selected_choice),
                    'is_correct': is_correct,
                    'score': score,
                    'completed': True
                }
            )

            # Update TaskSubmission to track completed content
            task_submission, _ = TaskSubmission.objects.get_or_create(
                task=task,
                student=request.user,
                defaults={'status': 'completed', 'completed_content': {}}
            )

            # Update completed_content JSON field
            completed_content = task_submission.completed_content or {}
            if not isinstance(completed_content, dict):
                completed_content = {}

            if 'question' not in completed_content:
                completed_content['question'] = []

            if question.id not in completed_content['question']:
                completed_content['question'].append(question.id)

            # Assign back to trigger Django's change detection
            task_submission.completed_content = completed_content
            task_submission.save(update_fields=['completed_content'])

            # Update enrollment progress
            try:
                enrollment = Enrollment.objects.get(student=request.user, course=task.course)
                enrollment.calculate_progress()
            except Enrollment.DoesNotExist:
                pass

            response_data = {
                'question_id': question.id,
                'selected_choice': selected_choice,
                'is_correct': is_correct,
                'correct_choices': correct_choices,
                'solution_explanation': mcq_details.solution_explanation or "No explanation provided",
                'score': float(score),
                'completed': True,
                'submitted_at': submission.submitted_at.isoformat()
            }

            return Response({
                'success': True,
                'message': 'MCQ answer submitted successfully',
                'data': response_data
            }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error submitting MCQ: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_coding_question(request, task_id):
    """
    Submit coding question solution - executes against ALL test cases
    POST /api/student/tasks/{task_id}/submit-coding/
    Body: {"question_id": 123, "code": "def solution()...", "language": "python"}
    """
    task = get_object_or_404(Task, id=task_id)

    # Check enrollment
    if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
        return Response({
            'success': False,
            'message': 'You are not enrolled in this course'
        }, status=status.HTTP_403_FORBIDDEN)

    # Validate input
    serializer = CodingSubmissionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid submission data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    question_id = serializer.validated_data['question_id']
    code = serializer.validated_data['code']
    language = request.data.get('language', 'python')

    question = get_object_or_404(TaskQuestion, id=question_id, task=task)

    if question.question_type != 'coding':
        return Response({
            'success': False,
            'message': 'Question is not a coding question'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        from courses.models import TaskTestCase

        # Get ALL test cases (sample + hidden)
        test_cases = question.coding_details.test_cases.all().order_by('-is_sample', 'order')

        # If no test cases exist, use sample from coding_details
        if not test_cases.exists():
            sample_input = question.coding_details.sample_input or ''
            sample_output = (question.coding_details.sample_output or '').strip()

            result = _run_code_in_sandbox(code, sample_input, language)
            user_output_raw = result.get('output', '')

            # Handle "No output" case - treat it as empty string
            if user_output_raw == "No output" or not user_output_raw:
                user_output = ""
            else:
                user_output = user_output_raw.strip()

            # Check if output matches - both must have content and match exactly
            is_correct = bool(sample_output and user_output and user_output == sample_output)

            score = question.marks if is_correct else 0

            # Only save submission if test passes
            if is_correct:
                with transaction.atomic():
                    submission, created = ContentSubmission.objects.update_or_create(
                        student=request.user,
                        question=question,
                        defaults={
                            'task': task,
                            'submission_type': 'question',
                            'code_submitted': code,
                            'completed': True,
                            'is_correct': True,
                            'score': score
                        }
                    )

            return Response({
                'success': is_correct,
                'message': 'Test passed! Code saved.' if is_correct else 'Test failed. Please fix your code.',
                'overall_status': 'ACCEPTED' if is_correct else 'WRONG_ANSWER',
                'score': score if is_correct else 0,
                'max_score': question.marks,
                'passed_tests': 1 if is_correct else 0,
                'total_tests': 1,
                'runtime': result.get('runtime'),
                'memory_used': result.get('memory'),
                'results': [{
                    'input': sample_input,
                    'expected': sample_output,
                    'user_output': user_output,
                    'is_correct': is_correct,
                    'is_sample': True,
                    'hidden': False,
                    'status': 'ACCEPTED' if is_correct else 'WRONG_ANSWER',
                    'runtime': result.get('runtime'),
                    'memory': result.get('memory'),
                    'error': result.get('error')
                }],
                'all_tests_passed': is_correct
            }, status=status.HTTP_200_OK)

        # Execute against all test cases
        results = []
        total_runtime = 0
        total_memory = 0
        passed_tests = 0
        total_score_weight = sum(tc.score_weight for tc in test_cases)

        for test_case in test_cases:
            result = _run_code_in_sandbox(code, test_case.input_data, language)
            user_output_raw = result.get('output', '')

            # Handle "No output" case - treat it as empty string
            if user_output_raw == "No output" or not user_output_raw:
                user_output = ""
            else:
                user_output = user_output_raw.strip()

            expected_output = test_case.expected_output.strip()

            # Compare outputs - must match exactly
            is_correct = (user_output == expected_output)
            if is_correct:
                passed_tests += 1

            total_runtime += result.get('runtime', 0)
            total_memory = max(total_memory, result.get('memory', 0))

            results.append({
                'input': test_case.input_data if not test_case.hidden else 'Hidden',
                'expected': expected_output if not test_case.hidden else 'Hidden',
                'user_output': user_output if not test_case.hidden else ('Passed' if is_correct else 'Failed'),
                'is_correct': is_correct,
                'is_sample': test_case.is_sample,
                'hidden': test_case.hidden,
                'status': 'ACCEPTED' if is_correct else ('RUNTIME_ERROR' if result.get('error') else 'WRONG_ANSWER'),
                'runtime': result.get('runtime'),
                'memory': result.get('memory'),
                'error': result.get('error') if result.get('error') and not test_case.hidden else None
            })

        # Calculate score based on passed test cases
        if total_score_weight > 0:
            passed_weight = sum(tc.score_weight for tc, r in zip(test_cases, results) if r['is_correct'])
            score = int((passed_weight / total_score_weight) * question.marks)
        else:
            score = question.marks if passed_tests == len(test_cases) else 0

        # Determine overall status
        if passed_tests == len(test_cases):
            overall_status = 'ACCEPTED'
        elif passed_tests > 0:
            overall_status = 'PARTIAL'
        elif any(r.get('error') for r in results):
            overall_status = 'RUNTIME_ERROR'
        else:
            overall_status = 'WRONG_ANSWER'

        avg_runtime = total_runtime / len(results) if results else 0

        # Only save submission if ALL test cases pass
        all_tests_passed = (passed_tests == len(test_cases))

        if all_tests_passed:
            with transaction.atomic():
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    question=question,
                    defaults={
                        'task': task,
                        'submission_type': 'question',
                        'code_submitted': code,
                        'completed': True,
                        'is_correct': True,
                        'score': score
                    }
                )

        return Response({
            'success': all_tests_passed,
            'message': 'All tests passed! Code saved.' if all_tests_passed else 'Some tests failed. Please fix your code.',
            'overall_status': overall_status,
            'score': score if all_tests_passed else 0,
            'max_score': question.marks,
            'passed_tests': passed_tests,
            'total_tests': len(test_cases),
            'runtime': avg_runtime,
            'memory_used': total_memory,
            'results': results,
            'all_tests_passed': all_tests_passed
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'Error submitting code: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_code(request):
    """
    Run code against sample test cases (visible test cases only)
    POST /api/student/submissions/run/
    Body: {"code": "...", "language": "python", "task_question_id": 123}
    """
    code = request.data.get('code', '').strip()
    language = request.data.get('language', 'python')
    task_question_id = request.data.get('task_question_id')

    if not code:
        return Response({
            'success': False,
            'error': 'Code is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Run against test cases if task_question_id is provided
        if task_question_id:
            from courses.models import TaskQuestion, TaskTestCase
            question = get_object_or_404(TaskQuestion, id=task_question_id)

            if question.question_type == 'coding' and question.coding_details:
                # Get only sample/visible test cases
                test_cases = question.coding_details.test_cases.filter(is_sample=True).order_by('order')

                # If no sample test cases exist, use the sample input/output from coding_details
                if not test_cases.exists():
                    sample_input = question.coding_details.sample_input or ''
                    sample_output = (question.coding_details.sample_output or '').strip()

                    # Run the code
                    result = _run_code_in_sandbox(code, sample_input, language)
                    user_output_raw = result.get('output', '')

                    # Handle "No output" case - treat it as empty string
                    if user_output_raw == "No output" or not user_output_raw:
                        user_output = ""
                    else:
                        user_output = user_output_raw.strip()

                    # Check if output matches - both must have content and match exactly
                    is_correct = bool(sample_output and user_output and user_output == sample_output)

                    return Response({
                        'success': True,
                        'status': result.get('status'),
                        'output': user_output if user_output else 'No output',
                        'error': result.get('error'),
                        'runtime': result.get('runtime'),
                        'memory': result.get('memory'),
                        'results': [{
                            'input': sample_input,
                            'expected': sample_output,
                            'user_output': user_output if user_output else 'No output',
                            'is_correct': is_correct,
                            'is_sample': True,
                            'hidden': False,
                            'status': 'ACCEPTED' if is_correct else 'WRONG_ANSWER',
                            'runtime': result.get('runtime'),
                            'memory': result.get('memory')
                        }]
                    }, status=status.HTTP_200_OK)

                # Run against all sample test cases
                results = []
                total_runtime = 0
                passed_tests = 0

                for test_case in test_cases:
                    result = _run_code_in_sandbox(code, test_case.input_data, language)
                    user_output_raw = result.get('output', '')

                    # Handle "No output" case - treat it as empty string
                    if user_output_raw == "No output" or not user_output_raw:
                        user_output = ""
                    else:
                        user_output = user_output_raw.strip()
                    expected_output = test_case.expected_output.strip()

                    # Normalize outputs for comparison
                    is_correct = (user_output == expected_output)
                    if is_correct:
                        passed_tests += 1

                    total_runtime += result.get('runtime', 0)

                    results.append({
                        'input': test_case.input_data,
                        'expected': expected_output,
                        'user_output': user_output,
                        'is_correct': is_correct,
                        'is_sample': test_case.is_sample,
                        'hidden': test_case.hidden,
                        'status': 'ACCEPTED' if is_correct else ('RUNTIME_ERROR' if result.get('error') else 'WRONG_ANSWER'),
                        'runtime': result.get('runtime'),
                        'memory': result.get('memory'),
                        'error': result.get('error') if result.get('error') else None
                    })

                avg_runtime = total_runtime / len(results) if results else 0

                return Response({
                    'success': True,
                    'status': 'OK' if passed_tests == len(results) else 'PARTIAL',
                    'results': results,
                    'passed_tests': passed_tests,
                    'total_tests': len(results),
                    'runtime': avg_runtime
                }, status=status.HTTP_200_OK)

        # If no task_question_id, return error
        return Response({
            'success': False,
            'error': 'task_question_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': f'Execution failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_content_complete(request, task_id):
    """
    Mark document or video as completed (NO page submissions)
    POST /api/student/tasks/{task_id}/mark-complete/
    Body: {"content_type": "document", "content_id": 45}
    """
    task = get_object_or_404(Task, id=task_id)

    # Check enrollment
    if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
        return Response({
            'success': False,
            'message': 'You are not enrolled in this course'
        }, status=status.HTTP_403_FORBIDDEN)

    # Validate input
    serializer = ContentCompletionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    content_type = serializer.validated_data['content_type']
    content_id = serializer.validated_data['content_id']

    try:
        with transaction.atomic():
            # Determine content object and create submission
            if content_type == 'document':
                content_obj = get_object_or_404(TaskDocument, id=content_id, task=task)
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    document=content_obj,
                    defaults={
                        'task': task,
                        'submission_type': 'document',
                        'completed': True
                    }
                )
            elif content_type == 'video':
                content_obj = get_object_or_404(TaskVideo, id=content_id, task=task)
                submission, created = ContentSubmission.objects.update_or_create(
                    student=request.user,
                    video=content_obj,
                    defaults={
                        'task': task,
                        'submission_type': 'video',
                        'completed': True
                    }
                )
            else:
                return Response({
                    'success': False,
                    'message': 'Invalid content type. Only document and video can be marked complete.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Update TaskSubmission to track completed content
            task_submission, _ = TaskSubmission.objects.get_or_create(
                task=task,
                student=request.user,
                defaults={'status': 'completed', 'completed_content': {}}
            )

            # Update completed_content JSON field - ensure it's a dict
            completed_content = task_submission.completed_content or {}
            if not isinstance(completed_content, dict):
                completed_content = {}

            if content_type not in completed_content:
                completed_content[content_type] = []

            # Convert content_id to int to ensure consistency
            content_id_int = int(content_id)
            if content_id_int not in completed_content[content_type]:
                completed_content[content_type].append(content_id_int)

            # Assign back to trigger Django's change detection
            task_submission.completed_content = completed_content
            task_submission.save(update_fields=['completed_content'])

            # Update enrollment progress
            progress = 0
            try:
                enrollment = Enrollment.objects.get(student=request.user, course=task.course)
                enrollment.calculate_progress()
                progress = float(enrollment.progress_percentage)
            except Enrollment.DoesNotExist:
                progress = 0.0

            return Response({
                'success': True,
                'message': f'{content_type.capitalize()} marked as completed',
                'data': {
                    'content_type': content_type,
                    'content_id': content_id,
                    'completed': True,
                    'submitted_at': submission.submitted_at.isoformat(),
                    'progress': progress
                }
            }, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"\n❌ ERROR in mark_content_complete:")
        print(error_traceback)
        return Response({
            'success': False,
            'message': f'Error marking content complete: {str(e)}',
            'error_detail': str(e),
            'traceback': error_traceback if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_task_submissions(request, task_id):
    """
    Get all submissions for a task by current user
    GET /api/student/tasks/{task_id}/submissions/
    """
    task = get_object_or_404(Task, id=task_id)

    # Check enrollment
    if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
        return Response({
            'success': False,
            'message': 'You are not enrolled in this course'
        }, status=status.HTTP_403_FORBIDDEN)

    submissions = ContentSubmission.objects.filter(
        student=request.user,
        task=task
    ).select_related('question', 'document', 'video')

    serializer = ContentSubmissionSerializer(submissions, many=True)

    return Response({
        'success': True,
        'message': 'Submissions retrieved successfully.',
        'data': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reset_quiz_submissions(request, task_id):
    """
    Reset ONLY MCQ submissions for a task (reattempt quiz)
    Does NOT reset coding question submissions
    POST /api/student/tasks/{task_id}/reset-quiz/
    """
    task = get_object_or_404(Task, id=task_id)

    # Check enrollment
    if not Enrollment.objects.filter(student=request.user, course=task.course).exists():
        return Response({
            'success': False,
            'message': 'You are not enrolled in this course'
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        with transaction.atomic():
            # Delete ONLY MCQ submissions (not coding questions)
            # MCQ submissions have mcq_selected_choice set, coding has code_submitted
            deleted_count = ContentSubmission.objects.filter(
                student=request.user,
                task=task,
                submission_type='question',
                mcq_selected_choice__isnull=False  # Only MCQ questions
            ).delete()[0]

            return Response({
                'success': True,
                'message': f'Quiz reset successfully. {deleted_count} MCQ submissions removed.',
                'data': {'deleted_count': deleted_count}
            }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error resetting quiz: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# CONTENT PROGRESS TRACKING (Videos, Documents, Questions - NO PAGES)
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_content_complete(request):
    """
    Mark a content item (video/document/question) as completed
    POST /api/student/content/mark-complete/
    Body: {content_type, content_id, task_id, course_id}
    """
    from .serializers import MarkContentCompleteSerializer, ContentProgressSerializer
    from .models import ContentProgress
    from courses.models import Course, Enrollment

    serializer = MarkContentCompleteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    course_id = serializer.validated_data['course_id']
    task = serializer.validated_data['task']
    content_type = serializer.validated_data['content_type']
    content_id = serializer.validated_data['content_id']

    # Get course
    course = get_object_or_404(Course, id=course_id)

    # Mark content as completed
    progress = ContentProgress.mark_completed(
        user=user,
        course=course,
        task=task,
        content_type=content_type,
        content_id=content_id
    )

    # Recalculate enrollment progress
    try:
        enrollment = Enrollment.objects.get(student=user, course=course)
        enrollment.calculate_progress()
    except Enrollment.DoesNotExist:
        pass

    return Response({
        'success': True,
        'message': f'{content_type.capitalize()} marked as completed',
        'data': ContentProgressSerializer(progress).data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_progress(request, course_id):
    """
    Get course progress summary
    GET /api/student/courses/{course_id}/progress/
    """
    from .models import ContentProgress
    from courses.models import Course

    course = get_object_or_404(Course, id=course_id)
    user = request.user

    # Get progress summary
    completed_count, total_count, percentage = ContentProgress.get_course_progress(user, course)

    return Response({
        'success': True,
        'message': 'Course progress retrieved successfully',
        'data': {
            'completed_count': completed_count,
            'total_count': total_count,
            'percentage': percentage,
            'course_id': course.id,
            'course_title': course.title
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_content_progress_list(request, course_id):
    """
    Get list of completed content for a course
    GET /api/student/courses/{course_id}/content-progress/
    """
    from .models import ContentProgress
    from .serializers import ContentProgressSerializer
    from courses.models import Course

    course = get_object_or_404(Course, id=course_id)
    user = request.user

    # Get all progress records for this course
    progress_records = ContentProgress.objects.filter(
        user=user,
        course=course
    ).select_related('task')

    serializer = ContentProgressSerializer(progress_records, many=True)

    return Response({
        'success': True,
        'message': 'Content progress retrieved successfully',
        'data': serializer.data
    }, status=status.HTTP_200_OK)
