from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.interview.models import InterviewAnswer
from .models import Evaluation, AnswerWeaknessTag, AnswerStrengthTag
from .serializers import (
    EvaluationCreateSerializer,
    EvaluationSerializer,
    AnswerWeaknessTagSerializer,
    AnswerStrengthTagSerializer,
)


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
        
        evaluation = serializer.save()
        
        return Response(
            {
                'evaluation_id': str(evaluation.id),
                'answer_id': str(evaluation.answer.id),
                'evaluated_at': evaluation.evaluated_at,
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
