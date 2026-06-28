from collections import Counter

from django.db.models import Count
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.interview.models import InterviewSession
from apps.input.models import CoverLetter, JobDescription, ProjectExperience, ResumeMaster
from apps.report.models import ActionPlan, FinalReport

from .serializers import InterviewHistoryQuerySerializer, InterviewHistorySerializer


class InterviewHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query_serializer = InterviewHistoryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        limit = query_serializer.validated_data['limit']
        session_status = query_serializer.validated_data.get('status')

        sessions = (
            InterviewSession.objects.filter(user=request.user)
            .select_related('final_report')
            .annotate(
                question_count=Count('questions', distinct=True),
                answer_count=Count('answers', distinct=True),
            )
            .order_by('-created_at')
        )
        if session_status:
            sessions = sessions.filter(status=session_status)

        total = sessions.count()
        serializer = InterviewHistorySerializer(sessions[:limit], many=True)
        return Response({'total': total, 'results': serializer.data}, status=status.HTTP_200_OK)


class GrowthView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        interview_type = request.query_params.get('interview_type')
        sessions = (
            InterviewSession.objects
            .filter(user=request.user, status='completed')
            .select_related('final_report')
            .prefetch_related('answers__weakness_mappings__weakness_tag')
            .order_by('created_at')
        )
        if interview_type:
            sessions = sessions.filter(interview_type=interview_type)

        points = []
        for session in sessions:
            try:
                report = session.final_report
            except Exception:
                continue
            if report.status != FinalReport.STATUS_DONE or report.is_mock or report.evaluation_status != 'COMPLETED':
                continue
            score = report.overall_score
            if score is None:
                continue
            date = session.created_at.date()
            metrics = _extract_metrics(report)
            points.append({
                'session_id': str(session.id),
                'date': date.isoformat(),
                'label': f"{date.month}/{date.day}",
                'overall_score': score,
                'interview_type': session.interview_type,
                'prompt_versions': session.prompt_version_snapshot or {},
                'metrics': metrics,
                'average_answer_time': _average_answer_time(session),
                '_session': session,
                '_report': report,
            })

        if not points:
            return Response(
                {
                    'points': [],
                    'first_score': None,
                    'latest_score': None,
                    'delta': 0,
                    'improved_count': 0,
                    'summary': _build_summary(request.user, []),
                    'growth_comparison': {'available': False, 'reason': 'DATA_INSUFFICIENT'},
                    'weakness_trend': {'available': False, 'items': []},
                    'action_plans': _latest_action_plans(request.user),
                    'recent_activity': _recent_activity(request.user),
                    'interview_history': [],
                    'next_action': _next_action(request.user),
                    'insights': ['No evaluated real sessions yet.'],
                },
                status=status.HTTP_200_OK,
            )

        first_score = points[0]['overall_score']
        latest_score = points[-1]['overall_score']
        delta = latest_score - first_score

        def get_weakness_tags(session):
            tags = set()
            for answer in session.answers.all():
                for wm in answer.weakness_mappings.all():
                    tags.add(wm.weakness_tag.tag_name)
            return tags

        first_tags = get_weakness_tags(points[0]['_session'])
        latest_tags = get_weakness_tags(points[-1]['_session'])
        improved_count = len(first_tags - latest_tags)

        insights = _generate_insights(delta, improved_count, len(points))

        clean_points = [{k: v for k, v in p.items() if not k.startswith('_')} for p in points]

        return Response(
            {
                'points': clean_points,
                'first_score': first_score,
                'latest_score': latest_score,
                'delta': delta,
                'improved_count': improved_count,
                'summary': _build_summary(request.user, points),
                'growth_comparison': _growth_comparison(points),
                'weakness_trend': _weakness_trend(points),
                'action_plans': _latest_action_plans(request.user),
                'recent_activity': _recent_activity(request.user),
                'interview_history': _interview_history(points),
                'next_action': _next_action(request.user),
                'insights': insights,
            },
            status=status.HTTP_200_OK,
        )


def _generate_insights(delta: int, improved_count: int, session_count: int) -> list:
    insights = []
    if delta > 15:
        insights.append(f"Score improved by {delta} pts - strong growth!")
    elif delta > 0:
        insights.append(f"Score up {delta} pts from first session. Keep going!")
    elif delta == 0:
        insights.append("Score is holding steady.")
    else:
        insights.append(f"Score dropped {abs(delta)} pts. Focus on your weakness tags.")

    if improved_count >= 3:
        insights.append(f"{improved_count} weakness tags resolved - answer quality improving overall.")
    elif improved_count > 0:
        insights.append(f"{improved_count} weakness tag(s) resolved.")

    if session_count >= 5:
        insights.append("Consistent practice is paying off. Keep this pace!")
    elif session_count >= 2:
        insights.append("More sessions will reveal a clearer growth pattern.")

    return insights[:3]


def _extract_metrics(report):
    summary = report.summary or {}
    score_summary = summary.get('score_summary') or {}
    metrics = score_summary.get('metrics') or {}
    return {
        'expertise': metrics.get('technical_score'),
        'logic': metrics.get('bei_logic_score'),
        'specificity': metrics.get('specificity_score'),
        'delivery': metrics.get('speech_delivery_score'),
        'job_fit': metrics.get('job_fit_score'),
        'problem_solving': metrics.get('problem_solving_score'),
        'answer_completion': metrics.get('answer_completion_score'),
        'filler_words': metrics.get('total_filler_count'),
    }


def _average_answer_time(session):
    durations = [
        answer.speech_duration
        for answer in session.answers.all()
        if answer.speech_duration is not None
    ]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 2)


def _build_summary(user, points):
    try:
        profile = user.profile
    except Exception:
        profile = None
    profile_fields = [
        getattr(profile, 'career_type', None),
        getattr(profile, 'major_type', None),
        getattr(profile, 'desired_job', None),
        getattr(profile, 'career_year', None),
    ] if profile else []
    completed_fields = sum(1 for value in profile_fields if value not in (None, ''))
    completion = round(completed_fields / 4 * 100) if profile_fields else 0
    scores = [point['overall_score'] for point in points]
    latest_activity = max(
        [
            value for value in [
                user.last_login,
                JobDescription.objects.filter(user=user).order_by('-created_at').values_list('created_at', flat=True).first(),
                ResumeMaster.objects.filter(user=user).order_by('-updated_at').values_list('updated_at', flat=True).first(),
                InterviewSession.objects.filter(user=user).order_by('-updated_at').values_list('updated_at', flat=True).first(),
            ]
            if value is not None
        ],
        default=None,
    )
    return {
        'profile_completion': completion,
        'point_balance': getattr(user, 'point_balance', 0),
        'completed_interview_count': len(points),
        'average_interview_score': round(sum(scores) / len(scores), 1) if scores else None,
        'last_login': user.last_login,
        'recent_activity_at': latest_activity,
    }


def _weakness_tags(session):
    tags = []
    for answer in session.answers.all():
        for mapping in answer.weakness_mappings.all():
            tags.append(mapping.weakness_tag.tag_name)
    return tags


def _weakness_trend(points):
    if len(points) < 2:
        return {'available': False, 'items': []}
    midpoint = max(1, len(points) // 2)
    previous = points[:midpoint]
    recent = points[midpoint:]
    previous_counter = Counter(tag for point in previous for tag in _weakness_tags(point['_session']))
    recent_counter = Counter(tag for point in recent for tag in _weakness_tags(point['_session']))
    all_tags = set(previous_counter) | set(recent_counter)
    items = []
    for tag in all_tags:
        previous_ratio = previous_counter[tag] / max(sum(previous_counter.values()), 1)
        recent_ratio = recent_counter[tag] / max(sum(recent_counter.values()), 1)
        if recent_ratio < previous_ratio:
            status_label = 'IMPROVING'
        elif recent_ratio > previous_ratio:
            status_label = 'WORSENING'
        else:
            status_label = 'STABLE'
        items.append(
            {
                'tag': tag,
                'previous_ratio': round(previous_ratio, 3),
                'recent_ratio': round(recent_ratio, 3),
                'status': status_label,
            }
        )
    items.sort(key=lambda item: item['recent_ratio'], reverse=True)
    return {'available': True, 'items': items[:5]}


def _growth_comparison(points):
    if len(points) < 2:
        return {'available': False, 'reason': 'DATA_INSUFFICIENT'}
    previous = points[-2]
    current = points[-1]
    same_version = previous.get('prompt_versions') == current.get('prompt_versions')
    metric_delta = {}
    for key, value in current.get('metrics', {}).items():
        prev_value = previous.get('metrics', {}).get(key)
        metric_delta[key] = None if value is None or prev_value is None else round(value - prev_value, 2)
    return {
        'available': True,
        'previous_session_id': previous['session_id'],
        'current_session_id': current['session_id'],
        'overall_delta': current['overall_score'] - previous['overall_score'],
        'metric_delta': metric_delta,
        'prompt_version_warning': None if same_version else 'PROMPT_VERSION_DIFFERS',
    }


def _latest_action_plans(user):
    plans = (
        ActionPlan.objects
        .filter(report__session__user=user)
        .select_related('report', 'report__session')
        .order_by('-created_at', '-id')[:3]
    )
    return [
        {
            'action_plan_id': str(plan.id),
            'report_id': str(plan.report_id),
            'session_id': str(plan.report.session_id),
            'title': plan.title,
            'description': plan.description,
            'status': plan.status,
            'completed_at': plan.updated_at if plan.status == ActionPlan.STATUS_DONE else None,
            'source_tag': plan.source_tag,
        }
        for plan in plans
    ]


def _recent_activity(user):
    activities = []
    for jd in JobDescription.objects.filter(user=user).order_by('-created_at')[:3]:
        activities.append({'type': 'JD', 'created_at': jd.created_at, 'label': jd.position})
    for resume in ResumeMaster.objects.filter(user=user).order_by('-updated_at')[:3]:
        activities.append({'type': 'RESUME', 'created_at': resume.updated_at, 'label': resume.name})
    for session in InterviewSession.objects.filter(user=user).order_by('-created_at')[:3]:
        activities.append({'type': 'INTERVIEW_COMPLETE' if session.status == 'completed' else 'INTERVIEW_START', 'created_at': session.created_at, 'label': session.interview_type})
    for plan in ActionPlan.objects.filter(report__session__user=user).order_by('-created_at')[:3]:
        activities.append({'type': 'ACTION_PLAN', 'created_at': plan.created_at, 'label': plan.title})
    activities.sort(key=lambda item: item['created_at'], reverse=True)
    return activities[:10]


def _interview_history(points):
    return [
        {
            'session_id': point['session_id'],
            'date': point['date'],
            'interview_type': point['interview_type'],
            'overall_score': point['overall_score'],
            'prompt_versions': point['prompt_versions'],
        }
        for point in points[-5:]
    ]


def _next_action(user):
    try:
        user.profile
    except Exception:
        return {'code': 'COMPLETE_PROFILE', 'path': '/profile'}
    if not JobDescription.objects.filter(user=user).exists():
        return {'code': 'ADD_JOB_DESCRIPTION', 'path': '/jd'}
    if not ResumeMaster.objects.filter(user=user).exists():
        return {'code': 'ADD_RESUME', 'path': '/profile'}
    if not InterviewSession.objects.filter(user=user, status='completed').exists():
        return {'code': 'START_INTERVIEW', 'path': '/interview'}
    if ActionPlan.objects.filter(report__session__user=user).exclude(status=ActionPlan.STATUS_DONE).exists():
        return {'code': 'CONTINUE_ACTION_PLAN', 'path': '/mypage'}
    if ProjectExperience.objects.filter(user=user).exists() or CoverLetter.objects.filter(user=user).exists():
        return {'code': 'REVIEW_GROWTH', 'path': '/mypage'}
    return {'code': 'ADD_PROJECT_OR_COVER_LETTER', 'path': '/profile'}
