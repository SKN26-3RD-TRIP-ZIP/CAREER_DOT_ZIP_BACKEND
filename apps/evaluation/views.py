# apps/evaluation/views.py
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
    AnswerStrengthTag
)
from .serializers import (
    EvaluationCreateSerializer,
    EvaluationSerializer,
    AnswerWeaknessTagSerializer,
    AnswerStrengthTagSerializer,
)
# 💡 evaluation_service 엔진 반입
from .services.evaluation_services import EvaluationService


class EvaluationCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_answer(self, answer_id):
        """Get answer and verify ownership."""
        try:
            answer = InterviewAnswer.objects.get(id=answer_id, session__user=self.request.user)
            return answer
        except InterviewAnswer.DoesNotExist:
            return None

    def post(self, request):
        serializer = EvaluationCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        answer = serializer.validated_data.get('answer_id')
        
        # Verify ownership
        if not self.get_answer(answer.id):
            return Response({'detail': 'Answer not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)
        
        # 💡 [AI 파이프라인 연동에 필요한 필수 인자 파싱]
        question_type = answer.question.question_type if hasattr(answer.question, 'question_type') else "technical"
        llm_weakness_tags = request.data.get("answer_sufficiency", {}).get("answer_weakness_tags", [])

        # 🚀 [동기식 호출 수행]
        ai_result = EvaluationService.run_pipeline(
            answer_text=answer.answer_text,
            question_type=question_type,
            llm_weakness_tags=llm_weakness_tags
        )
        
        # 태그 매핑 리스트는 ORM 인서트를 위해 별도로 팝(Pop) 처리
        pipeline_tags = ai_result.pop("pipeline_tags", {"strengths": [], "weaknesses": []})

        # 🤝 [데이터 무결성 트랜잭션]
        with transaction.atomic():
            evaluation = Evaluation.objects.create(
                answer=answer,
                bei_score=ai_result["bei_score"],
                cbi_score=ai_result["cbi_score"],
                filler_words=ai_result["filler_words"],
                final_tech_score=ai_result["final_tech_score"],
                score_detail=ai_result["score_detail"]
            )
            
            # 🌟 [요구사항 반영] 1. 강점 태그 릴레이션 매핑 순회 저장
            for idx, s in enumerate(pipeline_tags.get("strengths", []), start=1):
                tag_obj, _ = StrengthTag.objects.get_or_create(
                    tag_name=s["tag_name"],
                    defaults={"description": s["description"]}
                )
                AnswerStrengthTag.objects.create(
                    answer=answer, # 컨텍스트 변수 일치
                    strength_tag=tag_obj,
                    reason=f"[{s['category']}] {s['description']}", # 포맷 가이드라인 충족
                    trigger_signal_log=s["trigger_signal"],  # models.py 필드 완벽 대응
                    priority_rank=idx # 자동 증분 랭크 할당
                )
                
            # 2. 약점 태그 릴레이션 매핑 순회 저장
            for idx, w in enumerate(pipeline_tags.get("weaknesses", []), start=1):
                tag_master, _ = WeaknessTag.objects.get_or_create(
                    tag_name=w["tag_name"],
                    defaults={"description": w["description"]}
                )
                AnswerWeaknessTag.objects.create(
                    answer=answer,
                    weakness_tag=tag_master,
                    reason=w["description"],
                    priority_rank=idx, # 약점도 순서 정렬 일관성 유지를 위해 idx 적용 가능
                    is_selected_for_followup=w.get("is_selected_for_followup", False)
                )
        
        # API 응답 스펙 규격 포맷 준수 리턴
        return Response(
            {
                'evaluation_id': str(evaluation.id),
                'answer_id': str(evaluation.answer.id),
                'evaluated_at': evaluation.evaluated_at,
                'final_tech_score': evaluation.final_tech_score,
            },
            status=status.HTTP_201_CREATED,
        )


class EvaluationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_answer(self, answer_id):
        """Get answer and verify ownership."""
        try:
            answer = InterviewAnswer.objects.get(id=answer_id, session__user=self.request.user)
            return answer
        except InterviewAnswer.DoesNotExist:
            return None

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


class WeaknessTagsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_answer(self, answer_id):
        """Get answer and verify ownership."""
        try:
            answer = InterviewAnswer.objects.get(id=answer_id, session__user=self.request.user)
            return answer
        except InterviewAnswer.DoesNotExist:
            return None

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


class StrengthTagsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_answer(self, answer_id):
        """Get answer and verify ownership."""
        try:
            answer = InterviewAnswer.objects.get(id=answer_id, session__user=self.request.user)
            return answer
        except InterviewAnswer.DoesNotExist:
            return None

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