from django.db.models import Count
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.interview.models import InterviewSession

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
        sessions = (
            InterviewSession.objects
            .filter(user=request.user)
            .select_related('final_report')
            .prefetch_related('answers__weakness_mappings__weakness_tag')
            .order_by('created_at')
        )

        points = []
        for session in sessions:
            try:
                report = session.final_report
            except Exception:
                continue
            score = report.overall_score
            if score is None:
                continue
            date = session.created_at.date()
            points.append({
                'session_id': str(session.id),
                'date': date.isoformat(),
                'label': f"{date.month}/{date.day}",
                'overall_score': score,
                '_session': session,
            })

        if not points:
            return Response(
                {
                    'points': [],
                    'first_score': None,
                    'latest_score': None,
                    'delta': 0,
                    'improved_count': 0,
                    'insights': ['No completed sessions yet. Start your first interview!'],
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

        clean_points = [{k: v for k, v in p.items() if k != '_session'} for p in points]

        return Response(
            {
                'points': clean_points,
                'first_score': first_score,
                'latest_score': latest_score,
                'delta': delta,
                'improved_count': improved_count,
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
