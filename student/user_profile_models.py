# student/user_profile_models.py
"""
Extended user profile models for leaderboard, rankings, and achievements
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Count, Q


class UserProfile(models.Model):
    """
    Extended profile for tracking user statistics and rankings
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    
    # Points and Rankings
    total_points = models.IntegerField(default=0, help_text="Total points earned")
    global_rank = models.IntegerField(null=True, blank=True, help_text="Global ranking position")
    college_rank = models.IntegerField(null=True, blank=True, help_text="College-wise ranking position")
    
    # Challenge Statistics
    challenges_solved = models.IntegerField(default=0, help_text="Total challenges solved")
    easy_solved = models.IntegerField(default=0, help_text="Easy challenges solved")
    medium_solved = models.IntegerField(default=0, help_text="Medium challenges solved")
    hard_solved = models.IntegerField(default=0, help_text="Hard challenges solved")
    
    # Company Challenge Statistics
    company_challenges_solved = models.IntegerField(default=0, help_text="Company challenges solved")
    
    # Streak Tracking
    current_streak = models.IntegerField(default=0, help_text="Current daily solving streak")
    longest_streak = models.IntegerField(default=0, help_text="Longest streak achieved")
    last_activity = models.DateField(null=True, blank=True, help_text="Last submission date")
    
    # Submission Stats
    total_submissions = models.IntegerField(default=0, help_text="Total submissions made")
    successful_submissions = models.IntegerField(default=0, help_text="Successful submissions")
    
    # Time Tracking
    total_time_spent_minutes = models.IntegerField(default=0, help_text="Total time spent coding")
    
    # Performance Metrics
    average_runtime_ms = models.FloatField(default=0.0, help_text="Average runtime of successful submissions")
    average_memory_kb = models.FloatField(default=0.0, help_text="Average memory usage")
    
    # Course Progress
    courses_enrolled = models.IntegerField(default=0)
    courses_completed = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        ordering = ['-total_points', 'global_rank']
        indexes = [
            models.Index(fields=['global_rank']),
            models.Index(fields=['college_rank']),
            models.Index(fields=['total_points']),
            models.Index(fields=['-total_points']),  # Desc index for leaderboard
        ]
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def update_streak(self):
        """Update the user's submission streak"""
        today = timezone.now().date()
        
        if self.last_activity:
            days_diff = (today - self.last_activity).days
            
            if days_diff == 0:
                # Same day, no change to streak
                pass
            elif days_diff == 1:
                # Consecutive day, increment streak
                self.current_streak += 1
                if self.current_streak > self.longest_streak:
                    self.longest_streak = self.current_streak
            else:
                # Streak broken, reset
                self.current_streak = 1
        else:
            # First activity
            self.current_streak = 1
        
        self.last_activity = today
        self.save()
    
    def calculate_accuracy(self):
        """Calculate submission success rate"""
        if self.total_submissions == 0:
            return 0
        return round((self.successful_submissions / self.total_submissions) * 100, 2)
    
    @property
    def accuracy_percentage(self):
        return self.calculate_accuracy()
    
    def get_rank_badge(self):
        """Get rank badge based on total points"""
        if self.total_points >= 5000:
            return '💎 Diamond'
        elif self.total_points >= 3000:
            return '👑 Platinum'
        elif self.total_points >= 2000:
            return '🥇 Gold'
        elif self.total_points >= 1000:
            return '🥈 Silver'
        elif self.total_points >= 500:
            return '🥉 Bronze'
        else:
            return '🆕 Newcomer'


class Badge(models.Model):
    """
    Achievement badges that users can earn
    """
    BADGE_TYPES = [
        ('MILESTONE', 'Milestone'),
        ('STREAK', 'Streak'),
        ('CHALLENGE', 'Challenge'),
        ('PERFORMANCE', 'Performance'),
        ('SPECIAL', 'Special'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="Emoji or icon class")
    badge_type = models.CharField(max_length=20, choices=BADGE_TYPES, default='MILESTONE')
    
    # Requirements
    points_required = models.IntegerField(default=0, null=True, blank=True)
    challenges_required = models.IntegerField(default=0, null=True, blank=True)
    streak_required = models.IntegerField(default=0, null=True, blank=True)
    
    # Badge properties
    rarity = models.CharField(max_length=20, choices=[
        ('COMMON', 'Common'),
        ('RARE', 'Rare'),
        ('EPIC', 'Epic'),
        ('LEGENDARY', 'Legendary'),
    ], default='COMMON')
    
    bonus_points = models.IntegerField(default=0, help_text="Bonus points awarded when earning this badge")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'badges'
        ordering = ['rarity', 'name']
    
    def __str__(self):
        return f"{self.icon} {self.name}"


class UserBadge(models.Model):
    """
    Badges earned by users
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='earned_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='user_badges')
    earned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_badges'
        unique_together = ('user', 'badge')
        ordering = ['-earned_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


class LeaderboardCache(models.Model):
    """
    Cached leaderboard data for performance optimization
    Updated periodically via scheduled task
    """
    LEADERBOARD_TYPES = [
        ('GLOBAL', 'Global'),
        ('COLLEGE', 'College'),
        ('COURSE', 'Course'),
        ('COMPANY', 'Company'),
    ]
    
    TIME_PERIODS = [
        ('ALL_TIME', 'All Time'),
        ('MONTHLY', 'Monthly'),
        ('WEEKLY', 'Weekly'),
        ('DAILY', 'Daily'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leaderboard_entries')
    leaderboard_type = models.CharField(max_length=20, choices=LEADERBOARD_TYPES, default='GLOBAL')
    time_period = models.CharField(max_length=20, choices=TIME_PERIODS, default='ALL_TIME')
    
    # Ranking Data
    rank = models.IntegerField()
    total_points = models.IntegerField()
    challenges_solved = models.IntegerField()
    badge_count = models.IntegerField(default=0)
    
    # Additional context (for filtered leaderboards)
    college_id = models.IntegerField(null=True, blank=True)
    course_slug = models.CharField(max_length=255, null=True, blank=True)
    company_slug = models.CharField(max_length=255, null=True, blank=True)
    
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'leaderboard_cache'
        ordering = ['leaderboard_type', 'time_period', 'rank']
        indexes = [
            models.Index(fields=['leaderboard_type', 'time_period', 'rank']),
            models.Index(fields=['user', 'leaderboard_type']),
        ]
    
    def __str__(self):
        return f"Rank {self.rank}: {self.user.username} ({self.leaderboard_type})"


class UserActivity(models.Model):
    """
    Daily activity log for tracking user engagement
    """
    ACTIVITY_TYPES = [
        ('SUBMISSION', 'Code Submission'),
        ('CHALLENGE_SOLVED', 'Challenge Solved'),
        ('COURSE_START', 'Course Started'),
        ('COURSE_COMPLETE', 'Course Completed'),
        ('BADGE_EARNED', 'Badge Earned'),
        ('LOGIN', 'Login'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    activity_date = models.DateField(default=timezone.now)
    
    # Activity Details (JSON for flexibility)
    details = models.JSONField(default=dict, blank=True)
    
    # Points earned from this activity
    points_earned = models.IntegerField(default=0)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_activities'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'activity_date']),
            models.Index(fields=['activity_type']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.activity_type} on {self.activity_date}"
