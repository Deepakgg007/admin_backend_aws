# Dashboard Views for Student Stats
# Leaderboard and Company Progress

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Sum, Q, Max, F
from .models import CodingChallengeSubmission, CompanyChallengeSubmission


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def coding_challenge_leaderboard(request):
    """
    Get leaderboard for coding challenges
    GET /api/student/dashboard/leaderboard/

    Returns users ranked by:
    - Total score (sum of best submissions)
    - Problems solved (count of accepted challenges)
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Get all users with their coding challenge stats
    users_stats = []

    for user in User.objects.filter(is_active=True):
        # Get best submissions (highest score for each challenge)
        best_submissions = CodingChallengeSubmission.objects.filter(
            user=user,
            is_best_submission=True,
            status='ACCEPTED'
        )

        total_score = sum(sub.score for sub in best_submissions)
        problems_solved = best_submissions.count()

        if problems_solved > 0:  # Only include users who solved at least one problem
            users_stats.append({
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'total_score': total_score,
                'problems_solved': problems_solved,
            })

    # Sort by total_score DESC, then problems_solved DESC
    users_stats.sort(key=lambda x: (-x['total_score'], -x['problems_solved']))

    # Add rank
    for rank, user_stat in enumerate(users_stats, start=1):
        user_stat['rank'] = rank

    # Get current user's rank
    current_user_rank = None
    for user_stat in users_stats:
        if user_stat['user_id'] == request.user.id:
            current_user_rank = user_stat
            break

    return Response({
        'success': True,
        'leaderboard': users_stats[:100],  # Top 100
        'current_user': current_user_rank,
        'total_participants': len(users_stats),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_challenge_progress(request):
    """
    Get user's progress across all company challenges
    GET /api/student/dashboard/company-progress/

    Returns:
    - List of companies with progress (challenges solved per company)
    - Grouped by company
    """
    user = request.user

    # Get all company submissions for this user
    submissions = CompanyChallengeSubmission.objects.filter(user=user)

    # Group by company
    company_stats = {}

    for sub in submissions:
        company_id = sub.company_id
        company_name = sub.company_name

        if company_id not in company_stats:
            company_stats[company_id] = {
                'company_id': company_id,
                'company_name': company_name,
                'total_attempted': 0,
                'total_solved': 0,
                'total_score': 0,
                'concepts': {},
            }

        # Track by concept
        concept_id = sub.concept_id
        concept_name = sub.concept_name

        if concept_id not in company_stats[company_id]['concepts']:
            company_stats[company_id]['concepts'][concept_id] = {
                'concept_id': concept_id,
                'concept_name': concept_name,
                'attempted': 0,
                'solved': 0,
                'score': 0,
            }

        # Count unique challenges attempted
        if sub.is_best_submission:
            company_stats[company_id]['total_attempted'] += 1
            company_stats[company_id]['concepts'][concept_id]['attempted'] += 1

            if sub.status == 'ACCEPTED':
                company_stats[company_id]['total_solved'] += 1
                company_stats[company_id]['total_score'] += sub.score
                company_stats[company_id]['concepts'][concept_id]['solved'] += 1
                company_stats[company_id]['concepts'][concept_id]['score'] += sub.score

    # Convert to list
    company_progress = []
    for company_id, stats in company_stats.items():
        stats['concepts'] = list(stats['concepts'].values())
        company_progress.append(stats)

    # Sort by total_solved DESC
    company_progress.sort(key=lambda x: -x['total_solved'])

    return Response({
        'success': True,
        'companies': company_progress,
        'total_companies': len(company_progress),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_dashboard_stats(request):
    """
    Get comprehensive dashboard stats for current user
    GET /api/student/dashboard/stats/

    Returns:
    - Coding challenge stats (rank, score, problems solved)
    - Company challenge stats (companies attempted, challenges solved)
    - Recent activity
    """
    user = request.user

    # Coding Challenge Stats
    coding_submissions = CodingChallengeSubmission.objects.filter(
        user=user,
        is_best_submission=True,
        status='ACCEPTED'
    )

    coding_stats = {
        'total_score': sum(sub.score for sub in coding_submissions),
        'problems_solved': coding_submissions.count(),
        'total_attempted': CodingChallengeSubmission.objects.filter(
            user=user
        ).values('challenge').distinct().count(),
    }

    # Company Challenge Stats
    company_submissions = CompanyChallengeSubmission.objects.filter(user=user)

    company_stats = {
        'companies_attempted': company_submissions.values('company_id').distinct().count(),
        'challenges_solved': company_submissions.filter(
            status='ACCEPTED',
            is_best_submission=True
        ).count(),
        'total_score': sum(
            sub.score for sub in company_submissions.filter(
                status='ACCEPTED',
                is_best_submission=True
            )
        ),
    }

    # Recent Activity (last 10 submissions)
    recent_coding = CodingChallengeSubmission.objects.filter(
        user=user
    ).select_related('challenge').order_by('-submitted_at')[:5]

    recent_company = CompanyChallengeSubmission.objects.filter(
        user=user
    ).order_by('-submitted_at')[:5]

    recent_activity = []

    for sub in recent_coding:
        recent_activity.append({
            'type': 'coding',
            'challenge_title': sub.challenge.title,
            'status': sub.status,
            'score': sub.score,
            'submitted_at': sub.submitted_at,
        })

    for sub in recent_company:
        recent_activity.append({
            'type': 'company',
            'challenge_title': sub.challenge_title,
            'company_name': sub.company_name,
            'status': sub.status,
            'score': sub.score,
            'submitted_at': sub.submitted_at,
        })

    # Sort by time
    recent_activity.sort(key=lambda x: x['submitted_at'], reverse=True)

    return Response({
        'success': True,
        'coding_stats': coding_stats,
        'company_stats': company_stats,
        'recent_activity': recent_activity[:10],
    })
