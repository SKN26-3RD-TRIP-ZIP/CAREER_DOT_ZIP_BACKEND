from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.interview.models import InterviewAnswer
from .models import Evaluation
from .ab_test_models import ABTestExperiment
from .services.ab_test_service import get_experiment_stats
from .serializers import (
    EvaluationCreateSerializer,
    EvaluationSerializer,
    AnswerWeaknessTagSerializer,
    AnswerStrengthTagSerializer,
)
from .services.session_evaluation import create_evaluation_for_answer


class EvaluationAnswerMixin:
  def get_answer(self, answer_id):
    try:
      return InterviewAnswer.objects.get(id=answer_id, session__user=self.request.user)
    except InterviewAnswer.DoesNotExist:
      return None


class EvaluationCreateView(EvaluationAnswerMixin, APIView):
  permission_classes = [permissions.IsAuthenticated]

  def post(self, request):
    serializer = EvaluationCreateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)

    answer = serializer.validated_data['answer_id']
    request_sufficiency = request.data.get('answer_sufficiency')

    evaluation = create_evaluation_for_answer(
        answer,
        request_sufficiency=request_sufficiency,
    )

    return Response(
        {
            'evaluation_id': str(evaluation.id),
            'answer_id': str(evaluation.answer.id),
            'evaluated_at': evaluation.evaluated_at,
            'final_tech_score': evaluation.final_tech_score,
        },
        status=status.HTTP_201_CREATED,
    )


class EvaluationDetailView(EvaluationAnswerMixin, APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request, answer_id):
    answer = self.get_answer(answer_id)
    if not answer:
      return Response({'detail': 'Answer not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

    try:
      evaluation = answer.evaluation
    except Evaluation.DoesNotExist:
      return Response({'detail': 'Evaluation not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = EvaluationSerializer(evaluation)
    return Response(serializer.data, status=status.HTTP_200_OK)


class WeaknessTagsView(EvaluationAnswerMixin, APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request, answer_id):
    answer = self.get_answer(answer_id)
    if not answer:
      return Response({'detail': 'Answer not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

    weakness_tags = answer.weakness_mappings.select_related('weakness_tag').order_by('priority_rank')
    serializer = AnswerWeaknessTagSerializer(weakness_tags, many=True)

    return Response(
        {
            'answer_id': str(answer.id),
            'weakness_tags': serializer.data,
        },
        status=status.HTTP_200_OK,
    )


class StrengthTagsView(EvaluationAnswerMixin, APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request, answer_id):
    answer = self.get_answer(answer_id)
    if not answer:
      return Response({'detail': 'Answer not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

    strength_tags = answer.strength_mappings.select_related('strength_tag').order_by('priority_rank')
    serializer = AnswerStrengthTagSerializer(strength_tags, many=True)

    return Response(
        {
            'answer_id': str(answer.id),
            'strength_tags': serializer.data,
        },
        status=status.HTTP_200_OK,
    )


# -- E7.7 A/B 테스트 관리 API -----------------------------------------------
class ABTestExperimentListView(APIView):
    """GET /evaluations/ab-tests -- 전체 실험 목록 + 집계 통계."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        experiments = ABTestExperiment.objects.all().order_by('-created_at')
        results = [get_experiment_stats(exp.name) for exp in experiments]
        return Response({'total': len(results), 'results': results}, status=status.HTTP_200_OK)


class ABTestExperimentDetailView(APIView):
    """GET /evaluations/ab-tests/<experiment_name> -- 단일 실험 집계."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, experiment_name: str):
        stats = get_experiment_stats(experiment_name)
        if 'error' in stats:
            return Response(stats, status=status.HTTP_404_NOT_FOUND)
        return Response(stats, status=status.HTTP_200_OK)
P_404_NOT_FOUND)
    return Response(stats, status=status.HTTP_200_OK)
