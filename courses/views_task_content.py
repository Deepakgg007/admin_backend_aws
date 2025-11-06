"""
API Views for Task Content Management
Handles CRUD operations for:
- TaskDocument
- TaskVideo
- TaskQuestion (MCQ & Coding)
- TaskRichTextPage and its blocks
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

from .models import (
    Task, TaskDocument, TaskVideo, TaskQuestion, TaskMCQ, TaskCoding,
    TaskRichTextPage, TaskTextBlock, TaskCodeBlock, TaskVideoBlock
)
from .serializers import (
    TaskDocumentSerializer, TaskVideoSerializer,
    TaskQuestionSerializer, TaskQuestionCreateSerializer,
    TaskMCQSerializer, TaskCodingSerializer,
    TaskRichTextPageSerializer,
    TaskTextBlockSerializer, TaskCodeBlockSerializer, TaskVideoBlockSerializer
)


class TaskDocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing task documents

    list: Get all documents for a task
    create: Upload a new document
    retrieve: Get document details
    update/partial_update: Update document
    destroy: Delete document
    reorder: Reorder documents
    """
    serializer_class = TaskDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = TaskDocument.objects.all()
        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return queryset.select_related('task').order_by('order', 'uploaded_at')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """
        Reorder documents
        Expected payload: [{"id": 1, "order": 0}, {"id": 2, "order": 1}, ...]
        """
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                doc = TaskDocument.objects.get(id=item['id'])
                doc.order = item['order']
                doc.save(update_fields=['order'])
            except TaskDocument.DoesNotExist:
                continue

        return Response({'message': 'Documents reordered successfully'}, status=status.HTTP_200_OK)


class TaskVideoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing task videos

    list: Get all videos for a task
    create: Upload/add a new video
    retrieve: Get video details
    update/partial_update: Update video
    destroy: Delete video
    reorder: Reorder videos
    """
    serializer_class = TaskVideoSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = TaskVideo.objects.all()
        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return queryset.select_related('task').order_by('order', 'uploaded_at')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder videos"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                video = TaskVideo.objects.get(id=item['id'])
                video.order = item['order']
                video.save(update_fields=['order'])
            except TaskVideo.DoesNotExist:
                continue

        return Response({'message': 'Videos reordered successfully'}, status=status.HTTP_200_OK)


class TaskQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing task questions (MCQ & Coding)

    list: Get all questions for a task
    create: Create a new question with details
    retrieve: Get question with MCQ/Coding details
    update/partial_update: Update question
    destroy: Delete question
    reorder: Reorder questions
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TaskQuestionCreateSerializer
        return TaskQuestionSerializer

    def get_queryset(self):
        queryset = TaskQuestion.objects.all()
        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return queryset.select_related('task').prefetch_related(
            'mcq_details', 'coding_details'
        ).order_by('order', 'created_at')

    def create(self, request, *args, **kwargs):
        """Create a new question with detailed error messages"""
        print("=== Question Create Request ===")
        print(f"Request data: {request.data}")

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            print(f"Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            print(f"Error creating question: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """Update a question with detailed error messages"""
        print("=== Question Update Request ===")
        print(f"Request data: {request.data}")

        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            print(f"Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error updating question: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder questions"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                question = TaskQuestion.objects.get(id=item['id'])
                question.order = item['order']
                question.save(update_fields=['order'])
            except TaskQuestion.DoesNotExist:
                continue

        return Response({'message': 'Questions reordered successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['put', 'patch'], url_path='update-mcq')
    def update_mcq(self, request, pk=None):
        """Update MCQ details for a question"""
        question = self.get_object()

        if question.question_type != 'mcq':
            return Response(
                {'error': 'This question is not an MCQ'},
                status=status.HTTP_400_BAD_REQUEST
            )

        mcq = get_object_or_404(TaskMCQ, question=question)
        serializer = TaskMCQSerializer(mcq, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['put', 'patch'], url_path='update-coding')
    def update_coding(self, request, pk=None):
        """Update coding details for a question"""
        question = self.get_object()

        if question.question_type != 'coding':
            return Response(
                {'error': 'This question is not a coding question'},
                status=status.HTTP_400_BAD_REQUEST
            )

        coding = get_object_or_404(TaskCoding, question=question)
        serializer = TaskCodingSerializer(coding, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaskRichTextPageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing rich text pages

    list: Get all pages for a task
    create: Create a new page
    retrieve: Get page with all blocks
    update/partial_update: Update page
    destroy: Delete page
    reorder: Reorder pages
    """
    serializer_class = TaskRichTextPageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TaskRichTextPage.objects.all()
        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return queryset.select_related('task').prefetch_related(
            'text_blocks', 'code_blocks', 'video_blocks'
        ).order_by('order', 'created_at')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder pages"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                page = TaskRichTextPage.objects.get(id=item['id'])
                page.order = item['order']
                page.save(update_fields=['order'])
            except TaskRichTextPage.DoesNotExist:
                continue

        return Response({'message': 'Pages reordered successfully'}, status=status.HTTP_200_OK)


class TaskTextBlockViewSet(viewsets.ModelViewSet):
    """ViewSet for managing text blocks within pages"""
    serializer_class = TaskTextBlockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TaskTextBlock.objects.all()
        page_id = self.request.query_params.get('page')
        if page_id:
            queryset = queryset.filter(page_id=page_id)
        return queryset.select_related('page').order_by('order')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder text blocks"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                block = TaskTextBlock.objects.get(id=item['id'])
                block.order = item['order']
                block.save(update_fields=['order'])
            except TaskTextBlock.DoesNotExist:
                continue

        return Response({'message': 'Text blocks reordered successfully'}, status=status.HTTP_200_OK)


class TaskCodeBlockViewSet(viewsets.ModelViewSet):
    """ViewSet for managing code blocks within pages"""
    serializer_class = TaskCodeBlockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TaskCodeBlock.objects.all()
        page_id = self.request.query_params.get('page')
        if page_id:
            queryset = queryset.filter(page_id=page_id)
        return queryset.select_related('page').order_by('order')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder code blocks"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                block = TaskCodeBlock.objects.get(id=item['id'])
                block.order = item['order']
                block.save(update_fields=['order'])
            except TaskCodeBlock.DoesNotExist:
                continue

        return Response({'message': 'Code blocks reordered successfully'}, status=status.HTTP_200_OK)


class TaskVideoBlockViewSet(viewsets.ModelViewSet):
    """ViewSet for managing video blocks within pages"""
    serializer_class = TaskVideoBlockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TaskVideoBlock.objects.all()
        page_id = self.request.query_params.get('page')
        if page_id:
            queryset = queryset.filter(page_id=page_id)
        return queryset.select_related('page').order_by('order')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder video blocks"""
        order_data = request.data.get('items', [])

        for item in order_data:
            try:
                block = TaskVideoBlock.objects.get(id=item['id'])
                block.order = item['order']
                block.save(update_fields=['order'])
            except TaskVideoBlock.DoesNotExist:
                continue

        return Response({'message': 'Video blocks reordered successfully'}, status=status.HTTP_200_OK)
