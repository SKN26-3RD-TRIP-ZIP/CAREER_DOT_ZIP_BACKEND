from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from apps.interview.models import InterviewAnswer
from .models import (
    Evaluation,
    StrengthTag,
    WeaknessTag,
    AnswerWeaknessTag,
    AnswerStrengthTag,
)
from .serializers import (
    EvaluationCreateSerializer,
    EvaluationSerializer,
    AnswerWeaknessTagSerializer,
    AnswerStrengthTagSerializer,
)
from .services.evaluation_services import EvaluationService
from .services.sufficiency_bridge import (
    get_answer_text_for_evaluation,
    resolve_answer_sufficiency,
)


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
    answer_text = get_answer_text_for_evaluation(answer)
    question_type = answer.session.interview_type or 'technical'

    request_sufficiency = request.data.get('answer_sufficiency')
    llm_weakness_tags, selected_weakness_tag = resolve_answer_sufficiency(
        answer,
        request_sufficiency=request_sufficiency,
    )
    selected_tag_name = (
        selected_weakness_tag.get('tag_name')
        if isinstance(selected_weakness_tag, dict)
        else None
    )

    ai_result = EvaluationService.run_pipeline(
        answer_text=answer_text,
        question_type=question_type,
        long_pause_count=answer.long_pause_count or 0,
        llm_weakness_tags=llm_weakness_tags,
    )

    pipeline_tags = ai_result.pop('pipeline_tags', {'strengths': [], 'weaknesses': []})

    with transaction.atomic():
      evaluation = Evaluation.objects.create(
          answer=answer,
          bei_score=ai_result['bei_score'],
          cbi_score=ai_result['cbi_score'],
          filler_words=ai_result['filler_words'],
          final_tech_score=ai_result['final_tech_score'],
          score_detail=ai_result['score_detail'],
      )

      for idx, strength in enumerate(pipeline_tags.get('strengths', []), start=1):
        tag_obj, _ = StrengthTag.objects.get_or_create(
            tag_name=strength['tag_name'],
            defaults={'description': strength.get('description', '')},
        )
        AnswerStrengthTag.objects.create(
            answer=answer,
            strength_tag=tag_obj,
            reason=f"[{strength.get('category', 'general')}] {strength.get('description', '')}",
            trigger_signal_log=strength.get('trigger_signal', ''),
            priority_rank=idx,
        )

      for idx, weakness in enumerate(pipeline_tags.get('weaknesses', []), start=1):
        tag_master, _ = WeaknessTag.objects.get_or_create(
            tag_name=weakness['tag_name'],
            defaults={'description': weakness.get('description', '')},
        )
        tag_name = weakness.get('tag_name')
        AnswerWeaknessTag.objects.create(
            answer=answer,
            weakness_tag=tag_master,
            reason=weakness.get('description', ''),
            priority_rank=idx,
            is_selected_for_followup=(
                tag_name == selected_tag_name
                or weakness.get('is_selected_for_followup', False)
            ),
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
