"""
Django management command to backfill UserProfile statistics from existing submissions.

This command processes all existing CodingChallengeSubmission and CompanyChallengeSubmission
records and updates the corresponding UserProfile entries with accurate statistics.

Usage:
    python manage.py backfill_user_profiles
    python manage.py backfill_user_profiles --user-id=123  # For specific user
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from student.models import CodingChallengeSubmission, CompanyChallengeSubmission
from student.user_profile_models import UserProfile, UserActivity
from django.utils import timezone
from django.db import models as django_models

User = get_user_model()


class Command(BaseCommand):
    help = 'Backfill UserProfile statistics from existing challenge submissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Backfill for a specific user ID only',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset all profiles before backfilling',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        reset = options.get('reset', False)

        # Get users to process
        if user_id:
            users = User.objects.filter(id=user_id)
            if not users.exists():
                raise CommandError(f'User with ID {user_id} not found')
        else:
            users = User.objects.all()

        self.stdout.write(f'Processing {users.count()} users...')

        # Reset profiles if requested
        if reset:
            self.stdout.write(self.style.WARNING('Resetting all user profiles...'))
            UserProfile.objects.all().update(
                total_submissions=0,
                successful_submissions=0,
                challenges_solved=0,
                easy_solved=0,
                medium_solved=0,
                hard_solved=0,
                company_challenges_solved=0,
                total_points=0,
                current_streak=0,
                last_activity=None,
                average_runtime_ms=0.0,
                average_memory_kb=0.0,
            )

        for user in users:
            self.stdout.write(f'\nProcessing user: {user.username}')
            self._backfill_user(user)

        self.stdout.write(self.style.SUCCESS('[OK] Backfill completed successfully'))

    def _backfill_user(self, user):
        """Backfill statistics for a single user"""
        profile, created = UserProfile.objects.get_or_create(user=user)

        if created:
            self.stdout.write(f'  Created new profile for {user.username}')
        else:
            self.stdout.write(f'  Updating profile for {user.username}')

        # Reset counters
        profile.total_submissions = 0
        profile.successful_submissions = 0
        profile.challenges_solved = 0
        profile.easy_solved = 0
        profile.medium_solved = 0
        profile.hard_solved = 0
        profile.company_challenges_solved = 0
        profile.total_points = 0

        # Process CodingChallengeSubmission
        coding_submissions = CodingChallengeSubmission.objects.filter(
            user=user
        ).order_by('submitted_at')

        coding_solved_challenges = set()
        activities_to_create = []

        for submission in coding_submissions:
            profile.total_submissions += 1

            if submission.status == 'ACCEPTED':
                profile.successful_submissions += 1

                # Track first solve of each challenge
                if submission.challenge.id not in coding_solved_challenges:
                    coding_solved_challenges.add(submission.challenge.id)
                    profile.challenges_solved += 1

                    # Update difficulty counts
                    difficulty = submission.challenge.difficulty.upper()
                    if difficulty == 'EASY':
                        profile.easy_solved += 1
                    elif difficulty == 'MEDIUM':
                        profile.medium_solved += 1
                    elif difficulty == 'HARD':
                        profile.hard_solved += 1

                    # Award points
                    points = self._calculate_points(submission)
                    profile.total_points += points

                    # Create activity record
                    activities_to_create.append(
                        UserActivity(
                            user=user,
                            activity_type='CHALLENGE_SOLVED',
                            activity_date=submission.submitted_at.date(),
                            details={
                                'challenge_id': submission.challenge.id,
                                'challenge_title': submission.challenge.title,
                                'difficulty': difficulty,
                                'language': submission.language,
                                'score': submission.score,
                            },
                            points_earned=points,
                            timestamp=submission.submitted_at
                        )
                    )

        # Process CompanyChallengeSubmission
        company_submissions = CompanyChallengeSubmission.objects.filter(
            user=user
        ).order_by('submitted_at')

        for submission in company_submissions:
            profile.total_submissions += 1

            if submission.status == 'ACCEPTED':
                profile.successful_submissions += 1
                profile.company_challenges_solved += 1

                # Award points for company challenges
                points = 15  # Base points for company challenges
                if hasattr(user, 'profile'):
                    streak_bonus = min(profile.current_streak * 5, 50)
                    points += streak_bonus
                profile.total_points += points

                # Create activity record for company challenge
                activities_to_create.append(
                    UserActivity(
                        user=user,
                        activity_type='CHALLENGE_SOLVED',
                        activity_date=submission.submitted_at.date(),
                        details={
                            'company_id': submission.company_id,
                            'company_name': submission.company_name,
                            'challenge_id': submission.challenge_id,
                            'challenge_title': submission.challenge_title,
                            'language': submission.language,
                            'score': submission.score,
                        },
                        points_earned=points,
                        timestamp=submission.submitted_at
                    )
                )

        # Update streak based on last activity
        if profile.challenges_solved > 0:
            profile.update_streak(save=False)

        # Save profile
        profile.save()

        # Bulk create all activity records for this user
        if activities_to_create:
            UserActivity.objects.bulk_create(activities_to_create)
            self.stdout.write(self.style.SUCCESS(
                f'  [OK] Created {len(activities_to_create)} activity records'
            ))
        self.stdout.write(self.style.SUCCESS(
            f'  [OK] Total submissions: {profile.total_submissions}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  [OK] Challenges solved: {profile.challenges_solved} '
            f'(Easy: {profile.easy_solved}, Medium: {profile.medium_solved}, Hard: {profile.hard_solved})'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  [OK] Company challenges solved: {profile.company_challenges_solved}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  [OK] Current streak: {profile.current_streak}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  [OK] Total points: {profile.total_points}'
        ))

    def _calculate_points(self, submission):
        """Calculate points for a coding challenge submission"""
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
            multiplier = 1.5

        points = int(base_points * multiplier)

        # Streak bonus
        if hasattr(user, 'profile'):
            streak_bonus = min(user.profile.current_streak * 5, 50)
            points += streak_bonus

        return points
