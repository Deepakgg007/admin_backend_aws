# student/views_profile.py
"""
API views for user profile, leaderboard, and statistics
"""

from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum, Avg
from django.shortcuts import get_object_or_404

from .models import StudentChallengeSubmission
from .user_profile_models import UserProfile, Badge, UserBadge, UserActivity
from .serializers import (
    UserProfileSerializer, UserProfileStatsSerializer,
    LeaderboardEntrySerializer, UserActivitySerializer,
    BadgeSerializer, UserBadgeSerializer,
    ProgressStatsSerializer, CourseProgressSerializer
)
from coding.models import Challenge
from courses.models import Course, Enrollment

User = get_user_model()


class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user profiles
    
    Endpoints:
    - GET /api/student/profile/ - List all profiles (admin only)
    - GET /api/student/profile/me/ - Current user profile
    - GET /api/student/profile/{user_id}/ - Specific user profile (by user_id)
    - GET /api/student/profile/{user_id}/badges/ - User badges
    - GET /api/student/profile/{user_id}/activity/ - User activity
    - GET /api/student/profile/{user_id}/stats/ - User stats
    """
    queryset = UserProfile.objects.select_related('user').all()
    serializer_class = UserProfileSerializer
    permission_classes = [AllowAny]
    lookup_field = 'user_id'  # Look up by user_id instead of pk
    lookup_url_kwarg = 'pk'  # URL parameter name stays as 'pk' for router compatibility
    
    def get_object(self):
        """Override to look up profile by user_id from URL"""
        # Get the pk from URL (which is actually user_id)
        user_id = self.kwargs.get('pk')
        if user_id:
            # Look up by user_id in database
            profile = get_object_or_404(UserProfile, user_id=user_id)
            self.check_object_permissions(self.request, profile)
            return profile
        return super().get_object()
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user's profile"""
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(profile, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def badges(self, request, pk=None):
        """Get all badges earned by user"""
        profile = self.get_object()
        user_badges = UserBadge.objects.filter(user=profile.user).select_related('badge').order_by('-earned_at')
        serializer = UserBadgeSerializer(user_badges, many=True)
        return Response({
            'badges': serializer.data,
            'total_count': user_badges.count()
        })
    
    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """Get user's activity history"""
        profile = self.get_object()
        limit = int(request.query_params.get('limit', 50))
        
        activities = UserActivity.objects.filter(user=profile.user).order_by('-timestamp')[:limit]
        serializer = UserActivitySerializer(activities, many=True)
        
        return Response({
            'activities': serializer.data,
            'total_count': UserActivity.objects.filter(user=profile.user).count()
        })
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get detailed statistics for user"""
        profile = self.get_object()
        user = profile.user
        
        # Get submission stats
        total_submissions = StudentChallengeSubmission.objects.filter(user=user).count()
        accepted_submissions = StudentChallengeSubmission.objects.filter(
            user=user, status='ACCEPTED'
        ).count()
        
        # Get difficulty breakdown
        difficulty_stats = {
            'easy': {
                'solved': profile.easy_solved,
                'total': Challenge.objects.filter(difficulty__iexact='easy').count()
            },
            'medium': {
                'solved': profile.medium_solved,
                'total': Challenge.objects.filter(difficulty__iexact='medium').count()
            },
            'hard': {
                'solved': profile.hard_solved,
                'total': Challenge.objects.filter(difficulty__iexact='hard').count()
            }
        }
        
        # Recent submissions
        recent_submissions = StudentChallengeSubmission.objects.filter(
            user=user
        ).order_by('-submitted_at')[:10].values(
            'challenge__title', 'status', 'language', 'submitted_at', 'score'
        )
        
        # Calculate course stats and learning hours
        enrollments_queryset = Enrollment.objects.filter(student=user).select_related('course')
        total_enrollments = enrollments_queryset.count()

        # Recalculate progress for all enrollments to ensure status is up-to-date
        for enrollment in enrollments_queryset:
            enrollment.calculate_progress()

        # Re-query to get updated enrollments after progress calculation
        # Clear any cached querysets to ensure fresh data
        enrollments = Enrollment.objects.filter(student=user).select_related('course')

        # Additional check: Mark any enrollments with 100% progress as completed
        for enrollment in enrollments:
            if enrollment.progress_percentage >= 100 and enrollment.status != 'completed':
                enrollment.status = 'completed'
                if not enrollment.completed_at:
                    enrollment.completed_at = timezone.now()
                    # Update UserProfile courses_completed counter
                    from student.user_profile_models import UserProfile
                    profile_obj, created = UserProfile.objects.get_or_create(user=user)
                    profile_obj.courses_completed += 1
                    profile_obj.save(update_fields=['courses_completed'])
                enrollment.save(update_fields=['status', 'completed_at'])
        
        # Count completed enrollments: status='completed' OR progress_percentage >= 100
        completed_enrollments = enrollments.filter(
            Q(status='completed') | Q(progress_percentage__gte=100)
        ).count()
        
        # Get completed enrollments (status='completed' OR progress >= 100)
        completed_enrollments_list = enrollments.filter(
            Q(status='completed') | Q(progress_percentage__gte=100)
        )
        
        # Calculate learning hours
        total_course_hours = sum(enrollment.course.duration_hours or 0 for enrollment in enrollments)
        completed_course_hours = sum(
            enrollment.course.duration_hours or 0 
            for enrollment in completed_enrollments_list
        )
        
        # Calculate in-progress completed hours (based on progress percentage)
        # Exclude completed courses from in-progress calculation
        inprogress_enrollments = enrollments.exclude(
            Q(status='completed') | Q(progress_percentage__gte=100)
        )
        inprogress_completed_hours = sum(
            (enrollment.course.duration_hours or 0) * (float(enrollment.progress_percentage or 0)) / 100
            for enrollment in inprogress_enrollments
        )
        
        # Calculate overall completion percentage
        overall_completion_pct = 0
        if total_enrollments > 0:
            total_progress = sum(float(enrollment.progress_percentage or 0) for enrollment in enrollments)
            overall_completion_pct = round(total_progress / total_enrollments, 2)
        
        course_stats = {
            'total_enrollments': total_enrollments,
            'completed_enrollments': completed_enrollments,
            'overall_course_completion_pct': overall_completion_pct,
            'total_course_hours': total_course_hours,
            'completed_course_hours': round(completed_course_hours, 2),
            'inprogress_completed_hours': round(inprogress_completed_hours, 2),
            'hours_completed_overall': round(completed_course_hours + inprogress_completed_hours, 2)
        }
        
        return Response({
            'profile': UserProfileSerializer(profile).data,
            'submissions': {
                'total': total_submissions,
                'accepted': accepted_submissions,
                'accuracy': round((accepted_submissions / total_submissions * 100) if total_submissions > 0 else 0, 2)
            },
            'difficulty_breakdown': difficulty_stats,
            'recent_submissions': list(recent_submissions),
            'course_stats': course_stats
        })


class LeaderboardView(generics.ListAPIView):
    """
    Leaderboard API with filtering options
    
    Query Parameters:
    - type: global (default), college, course, company
    - time_period: all_time (default), monthly, weekly
    - limit: number of results (default 100)
    - college_id: filter by college
    - course_slug: filter by course
    """
    serializer_class = LeaderboardEntrySerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = UserProfile.objects.select_related('user').filter(
            challenges_solved__gt=0
        ).order_by('-total_points', 'user__username')
        
        # Filter by type
        leaderboard_type = self.request.query_params.get('type', 'global')
        
        if leaderboard_type == 'college':
            college_id = self.request.query_params.get('college_id')
            if college_id:
                queryset = queryset.filter(user__college_id=college_id)
        
        # Limit results
        limit = int(self.request.query_params.get('limit', 100))
        queryset = queryset[:limit]
        
        # Add rank annotation
        for idx, profile in enumerate(queryset, 1):
            profile.rank = idx
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # Add user's position if authenticated
        user_position = None
        if request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.get(user=request.user)
                user_position = {
                    'rank': user_profile.global_rank or 0,
                    'total_points': user_profile.total_points,
                    'challenges_solved': user_profile.challenges_solved
                }
            except UserProfile.DoesNotExist:
                pass
        
        return Response({
            'leaderboard': serializer.data,
            'user_position': user_position,
            'total_users': UserProfile.objects.filter(challenges_solved__gt=0).count()
        })


class GlobalLeaderboardView(generics.ListAPIView):
    """Global leaderboard - top performers"""
    serializer_class = LeaderboardEntrySerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        limit = int(self.request.query_params.get('limit', 100))
        return UserProfile.objects.select_related('user').filter(
            challenges_solved__gt=0
        ).order_by('-total_points')[:limit]


class CollegeLeaderboardView(generics.ListAPIView):
    """College-specific leaderboard"""
    serializer_class = LeaderboardEntrySerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        college_id = self.kwargs.get('college_id')
        limit = int(self.request.query_params.get('limit', 100))
        
        return UserProfile.objects.select_related('user').filter(
            user__college_id=college_id,
            challenges_solved__gt=0
        ).order_by('-total_points')[:limit]


class BadgeListView(generics.ListAPIView):
    """List all available badges"""
    queryset = Badge.objects.filter(is_active=True).order_by('rarity', 'points_required')
    serializer_class = BadgeSerializer
    permission_classes = [AllowAny]


class UserBadgesView(generics.ListAPIView):
    """Get badges for a specific user"""
    serializer_class = UserBadgeSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        return UserBadge.objects.filter(user_id=user_id).select_related('badge').order_by('-earned_at')


class ProgressStatsView(generics.GenericAPIView):
    """Get user's progress statistics"""
    permission_classes = [IsAuthenticated]
    serializer_class = ProgressStatsSerializer
    
    def get(self, request):
        user = request.user
        
        # Overall challenge progress
        total_challenges = Challenge.objects.filter(is_active=True).count()
        solved_challenges = StudentChallengeSubmission.objects.filter(
            user=user,
            status='ACCEPTED'
        ).values('challenge').distinct().count()
        
        # Difficulty breakdown
        easy_total = Challenge.objects.filter(difficulty__iexact='easy', is_active=True).count()
        medium_total = Challenge.objects.filter(difficulty__iexact='medium', is_active=True).count()
        hard_total = Challenge.objects.filter(difficulty__iexact='hard', is_active=True).count()
        
        profile = UserProfile.objects.get_or_create(user=user)[0]
        
        data = {
            'total_challenges': total_challenges,
            'solved_challenges': solved_challenges,
            'easy_total': easy_total,
            'easy_solved': profile.easy_solved,
            'medium_total': medium_total,
            'medium_solved': profile.medium_solved,
            'hard_total': hard_total,
            'hard_solved': profile.hard_solved,
            'completion_percentage': round((solved_challenges / total_challenges * 100) if total_challenges > 0 else 0, 2)
        }
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class ActivityFeedView(generics.ListAPIView):
    """User activity feed"""
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        days = int(self.request.query_params.get('days', 30))
        
        from datetime import timedelta
        from django.utils import timezone
        
        start_date = timezone.now() - timedelta(days=days)
        
        return UserActivity.objects.filter(
            user=user,
            timestamp__gte=start_date
        ).order_by('-timestamp')
