# student/signals.py
"""
Django signals for automatically updating user profiles and stats
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import models
from .models import StudentChallengeSubmission, CodingChallengeSubmission, CompanyChallengeSubmission
from .user_profile_models import UserProfile, UserActivity
from coding.models import Challenge

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a UserProfile when a new user is created
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save the user profile when the user is saved
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=StudentChallengeSubmission)
def update_profile_on_submission(sender, instance, created, **kwargs):
    """
    Update user profile statistics when a submission is made
    """
    if not created:
        return  # Only process new submissions
    
    user = instance.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # Update total submissions
    profile.total_submissions += 1
    
    # Update successful submissions and challenges solved
    if instance.status == 'ACCEPTED':
        profile.successful_submissions += 1
        
        # Check if this is the first accepted submission for this challenge
        previous_accepted = StudentChallengeSubmission.objects.filter(
            user=user,
            challenge=instance.challenge,
            status='ACCEPTED',
            submitted_at__lt=instance.submitted_at
        ).exists()
        
        if not previous_accepted:
            # First time solving this challenge
            profile.challenges_solved += 1
            
            # Update difficulty-wise counts
            difficulty = instance.challenge.difficulty.upper()
            if difficulty == 'EASY':
                profile.easy_solved += 1
            elif difficulty == 'MEDIUM':
                profile.medium_solved += 1
            elif difficulty == 'HARD':
                profile.hard_solved += 1
            
            # Award points based on difficulty
            points = calculate_challenge_points(instance)
            profile.total_points += points
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                activity_type='CHALLENGE_SOLVED',
                details={
                    'challenge_id': instance.challenge.id,
                    'challenge_title': instance.challenge.title,
                    'difficulty': difficulty,
                    'language': instance.language,
                    'score': instance.score,
                },
                points_earned=points
            )

            # Update streak (pass save=False to avoid double save)
            profile.update_streak(save=False)

    # Update average performance metrics
    update_performance_metrics(profile, user)

    profile.save()


def calculate_challenge_points(submission):
    """
    Calculate points awarded for solving a challenge
    
    Base Points:
    - Easy: 10 points
    - Medium: 20 points
    - Hard: 30 points
    
    Bonuses:
    - First attempt acceptance: +50%
    - Current streak bonus: +5 points per day
    """
    challenge = submission.challenge
    difficulty = challenge.difficulty.upper()
    
    # Base points
    base_points = {
        'EASY': 10,
        'MEDIUM': 20,
        'HARD': 30,
    }.get(difficulty, 10)
    
    # Check if first attempt
    user = submission.user
    previous_attempts = StudentChallengeSubmission.objects.filter(
        user=user,
        challenge=challenge,
        submitted_at__lt=submission.submitted_at
    ).count()
    
    multiplier = 1.0
    if previous_attempts == 0:
        # First attempt bonus
        multiplier = 1.5
    
    points = int(base_points * multiplier)
    
    # Streak bonus
    if hasattr(user, 'profile'):
        streak_bonus = min(user.profile.current_streak * 5, 50)  # Max 50 bonus points
        points += streak_bonus
    
    return points


def update_performance_metrics(profile, user):
    """
    Update average runtime and memory usage metrics
    """
    successful_submissions = StudentChallengeSubmission.objects.filter(
        user=user,
        status='ACCEPTED'
    )
    
    if successful_submissions.exists():
        avg_runtime = successful_submissions.aggregate(
            models.Avg('runtime')
        )['runtime__avg'] or 0
        
        avg_memory = successful_submissions.aggregate(
            models.Avg('memory_used')
        )['memory_used__avg'] or 0
        
        profile.average_runtime_ms = round(avg_runtime, 2)
        profile.average_memory_kb = round(avg_memory, 2)


# Badge checking function
def check_and_award_badges(user):
    """
    Check if user qualifies for any new badges and award them
    """
    from .user_profile_models import Badge, UserBadge
    
    profile = user.profile
    
    # Get all badges user doesn't have yet
    existing_badge_ids = UserBadge.objects.filter(user=user).values_list('badge_id', flat=True)
    available_badges = Badge.objects.filter(is_active=True).exclude(id__in=existing_badge_ids)
    
    newly_awarded = []
    
    for badge in available_badges:
        qualifies = True
        
        # Check points requirement
        if badge.points_required and profile.total_points < badge.points_required:
            qualifies = False
        
        # Check challenges requirement
        if badge.challenges_required and profile.challenges_solved < badge.challenges_required:
            qualifies = False
        
        # Check streak requirement
        if badge.streak_required and profile.current_streak < badge.streak_required:
            qualifies = False
        
        if qualifies:
            # Award the badge
            user_badge = UserBadge.objects.create(user=user, badge=badge)
            newly_awarded.append(badge)
            
            # Award bonus points
            if badge.bonus_points > 0:
                profile.total_points += badge.bonus_points
                profile.save()
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                activity_type='BADGE_EARNED',
                details={
                    'badge_name': badge.name,
                    'badge_icon': badge.icon,
                },
                points_earned=badge.bonus_points
            )
    
    return newly_awarded


# ============================================================================
# CODING CHALLENGE SUBMISSION SIGNAL - Updates UserProfile when challenge solved
# ============================================================================

@receiver(post_save, sender=CodingChallengeSubmission)
def update_profile_on_coding_challenge_submission(sender, instance, created, **kwargs):
    """
    Update user profile statistics when a coding challenge submission is made.
    This handles CodingChallengeSubmission model which is used for standalone
    coding challenges in the challenge platform.
    """
    if not created:
        return  # Only process new submissions

    user = instance.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Update total submissions
    profile.total_submissions += 1

    # Update successful submissions and challenges solved
    if instance.status == 'ACCEPTED':
        profile.successful_submissions += 1

        # Check if this is the first accepted submission for this challenge
        previous_accepted = CodingChallengeSubmission.objects.filter(
            user=user,
            challenge=instance.challenge,
            status='ACCEPTED',
            submitted_at__lt=instance.submitted_at
        ).exists()

        if not previous_accepted:
            # First time solving this challenge
            profile.challenges_solved += 1

            # Update difficulty-wise counts
            difficulty = instance.challenge.difficulty.upper()
            if difficulty == 'EASY':
                profile.easy_solved += 1
            elif difficulty == 'MEDIUM':
                profile.medium_solved += 1
            elif difficulty == 'HARD':
                profile.hard_solved += 1

            # Award points based on difficulty
            points = calculate_challenge_points_coding(instance)
            profile.total_points += points

            # Log activity
            UserActivity.objects.create(
                user=user,
                activity_type='CHALLENGE_SOLVED',
                details={
                    'challenge_id': instance.challenge.id,
                    'challenge_title': instance.challenge.title,
                    'difficulty': difficulty,
                    'language': instance.language,
                    'score': instance.score,
                },
                points_earned=points
            )

            # Update streak (pass save=False to avoid double save)
            profile.update_streak(save=False)

    # Update average performance metrics
    update_performance_metrics_coding(profile, user)

    profile.save()


# ============================================================================
# COMPANY CHALLENGE SUBMISSION SIGNAL - Updates UserProfile when challenge solved
# ============================================================================

@receiver(post_save, sender=CompanyChallengeSubmission)
def update_profile_on_company_challenge_submission(sender, instance, created, **kwargs):
    """
    Update user profile statistics when a company challenge submission is made.
    This handles CompanyChallengeSubmission model which is used for company-specific
    coding challenges in interview preparation.
    """
    if not created:
        return  # Only process new submissions

    user = instance.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Update total submissions
    profile.total_submissions += 1

    # Update successful submissions and challenges solved
    if instance.status == 'ACCEPTED':
        profile.successful_submissions += 1
        profile.company_challenges_solved += 1

        # Award points based on difficulty
        points = calculate_company_challenge_points(instance)
        profile.total_points += points

        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='CHALLENGE_SOLVED',
            details={
                'company_id': instance.company_id,
                'company_name': instance.company_name,
                'challenge_id': instance.challenge_id,
                'challenge_title': instance.challenge_title,
                'language': instance.language,
                'score': instance.score,
            },
            points_earned=points
        )

        # Update streak (pass save=False to avoid double save)
        profile.update_streak(save=False)

    # Update average performance metrics
    update_performance_metrics_company(profile, user)

    profile.save()


# ============================================================================
# HELPER FUNCTIONS FOR POINT CALCULATION AND METRICS
# ============================================================================

def calculate_challenge_points_coding(submission):
    """
    Calculate points awarded for solving a coding challenge.

    Base Points:
    - Easy: 10 points
    - Medium: 20 points
    - Hard: 30 points

    Bonuses:
    - First attempt acceptance: +50%
    - Current streak bonus: +5 points per day
    """
    challenge = submission.challenge
    difficulty = challenge.difficulty.upper()

    # Base points
    base_points = {
        'EASY': 10,
        'MEDIUM': 20,
        'HARD': 30,
    }.get(difficulty, 10)

    # Check if first attempt
    user = submission.user
    previous_attempts = CodingChallengeSubmission.objects.filter(
        user=user,
        challenge=challenge,
        submitted_at__lt=submission.submitted_at
    ).count()

    multiplier = 1.0
    if previous_attempts == 0:
        # First attempt bonus
        multiplier = 1.5

    points = int(base_points * multiplier)

    # Streak bonus
    if hasattr(user, 'profile'):
        streak_bonus = min(user.profile.current_streak * 5, 50)  # Max 50 bonus points
        points += streak_bonus

    return points


def calculate_company_challenge_points(submission):
    """
    Calculate points awarded for solving a company challenge.

    Base Points: 15 points per challenge
    Bonuses:
    - Current streak bonus: +5 points per day
    """
    base_points = 15

    user = submission.user
    multiplier = 1.0

    points = int(base_points * multiplier)

    # Streak bonus
    if hasattr(user, 'profile'):
        streak_bonus = min(user.profile.current_streak * 5, 50)  # Max 50 bonus points
        points += streak_bonus

    return points


def update_performance_metrics_coding(profile, user):
    """
    Update average runtime and memory usage metrics for coding challenges.
    """
    successful_submissions = CodingChallengeSubmission.objects.filter(
        user=user,
        status='ACCEPTED'
    )

    if successful_submissions.exists():
        avg_runtime = successful_submissions.aggregate(
            models.Avg('runtime')
        )['runtime__avg'] or 0

        avg_memory = successful_submissions.aggregate(
            models.Avg('memory_used')
        )['memory_used__avg'] or 0

        profile.average_runtime_ms = round(avg_runtime, 2)
        profile.average_memory_kb = round(avg_memory, 2)


def update_performance_metrics_company(profile, user):
    """
    Update performance metrics for company challenges.
    """
    successful_submissions = CompanyChallengeSubmission.objects.filter(
        user=user,
        status='ACCEPTED'
    )

    if successful_submissions.exists():
        avg_runtime = successful_submissions.aggregate(
            models.Avg('runtime')
        )['runtime__avg'] or 0

        avg_memory = successful_submissions.aggregate(
            models.Avg('memory_used')
        )['memory_used__avg'] or 0

        profile.average_runtime_ms = round(avg_runtime, 2)
        profile.average_memory_kb = round(avg_memory, 2)
