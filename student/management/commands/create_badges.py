# student/management/commands/create_badges.py
"""
Management command to create default badges
Usage: python manage.py create_badges
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from student.user_profile_models import Badge


class Command(BaseCommand):
    help = 'Create default achievement badges'

    def handle(self, *args, **kwargs):
        badges_data = [
            # Milestone Badges
            {
                'name': 'First Blood',
                'slug': 'first-blood',
                'description': 'Solve your first coding challenge',
                'icon': '🏆',
                'badge_type': 'MILESTONE',
                'challenges_required': 1,
                'rarity': 'COMMON',
                'bonus_points': 10,
            },
            {
                'name': 'Getting Started',
                'slug': 'getting-started',
                'description': 'Solve 5 challenges',
                'icon': '🎯',
                'badge_type': 'MILESTONE',
                'challenges_required': 5,
                'rarity': 'COMMON',
                'bonus_points': 25,
            },
            {
                'name': 'Problem Solver',
                'slug': 'problem-solver',
                'description': 'Solve 25 challenges',
                'icon': '💡',
                'badge_type': 'MILESTONE',
                'challenges_required': 25,
                'rarity': 'RARE',
                'bonus_points': 100,
            },
            {
                'name': 'Code Master',
                'slug': 'code-master',
                'description': 'Solve 50 challenges',
                'icon': '🎓',
                'badge_type': 'MILESTONE',
                'challenges_required': 50,
                'rarity': 'EPIC',
                'bonus_points': 250,
            },
            {
                'name': 'Coding Legend',
                'slug': 'coding-legend',
                'description': 'Solve 100 challenges',
                'icon': '👑',
                'badge_type': 'MILESTONE',
                'challenges_required': 100,
                'rarity': 'LEGENDARY',
                'bonus_points': 500,
            },
            
            # Points-based Badges
            {
                'name': 'Bronze Tier',
                'slug': 'bronze-tier',
                'description': 'Earn 500 points',
                'icon': '🥉',
                'badge_type': 'MILESTONE',
                'points_required': 500,
                'rarity': 'COMMON',
                'bonus_points': 50,
            },
            {
                'name': 'Silver Tier',
                'slug': 'silver-tier',
                'description': 'Earn 1000 points',
                'icon': '🥈',
                'badge_type': 'MILESTONE',
                'points_required': 1000,
                'rarity': 'RARE',
                'bonus_points': 100,
            },
            {
                'name': 'Gold Tier',
                'slug': 'gold-tier',
                'description': 'Earn 2000 points',
                'icon': '🥇',
                'badge_type': 'MILESTONE',
                'points_required': 2000,
                'rarity': 'EPIC',
                'bonus_points': 200,
            },
            {
                'name': 'Platinum Tier',
                'slug': 'platinum-tier',
                'description': 'Earn 3000 points',
                'icon': '💎',
                'badge_type': 'MILESTONE',
                'points_required': 3000,
                'rarity': 'LEGENDARY',
                'bonus_points': 300,
            },
            
            # Streak Badges
            {
                'name': 'Warming Up',
                'slug': 'warming-up',
                'description': 'Maintain a 3-day solving streak',
                'icon': '🔥',
                'badge_type': 'STREAK',
                'streak_required': 3,
                'rarity': 'COMMON',
                'bonus_points': 30,
            },
            {
                'name': 'On Fire',
                'slug': 'on-fire',
                'description': 'Maintain a 7-day solving streak',
                'icon': '🔥🔥',
                'badge_type': 'STREAK',
                'streak_required': 7,
                'rarity': 'RARE',
                'bonus_points': 70,
            },
            {
                'name': 'Unstoppable',
                'slug': 'unstoppable',
                'description': 'Maintain a 30-day solving streak',
                'icon': '🔥🔥🔥',
                'badge_type': 'STREAK',
                'streak_required': 30,
                'rarity': 'EPIC',
                'bonus_points': 300,
            },
            {
                'name': 'Dedication Machine',
                'slug': 'dedication-machine',
                'description': 'Maintain a 100-day solving streak',
                'icon': '⚡',
                'badge_type': 'STREAK',
                'streak_required': 100,
                'rarity': 'LEGENDARY',
                'bonus_points': 1000,
            },
            
            # Special Badges
            {
                'name': 'Early Bird',
                'slug': 'early-bird',
                'description': 'Join the platform in its early days',
                'icon': '🐦',
                'badge_type': 'SPECIAL',
                'rarity': 'RARE',
                'bonus_points': 50,
            },
            {
                'name': 'Rising Star',
                'slug': 'rising-star',
                'description': 'Reach top 100 in global leaderboard',
                'icon': '🌟',
                'badge_type': 'SPECIAL',
                'rarity': 'EPIC',
                'bonus_points': 200,
            },
            {
                'name': 'Top Performer',
                'slug': 'top-performer',
                'description': 'Reach top 10 in global leaderboard',
                'icon': '⭐',
                'badge_type': 'SPECIAL',
                'rarity': 'LEGENDARY',
                'bonus_points': 500,
            },
        ]

        created_count = 0
        updated_count = 0

        for badge_data in badges_data:
            badge, created = Badge.objects.update_or_create(
                slug=badge_data['slug'],
                defaults=badge_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created badge: {badge.name}'))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'↻ Updated badge: {badge.name}'))

        self.stdout.write(self.style.SUCCESS(f'\nSummary:'))
        self.stdout.write(self.style.SUCCESS(f'  Created: {created_count} badges'))
        self.stdout.write(self.style.WARNING(f'  Updated: {updated_count} badges'))
        self.stdout.write(self.style.SUCCESS(f'  Total: {len(badges_data)} badges'))
