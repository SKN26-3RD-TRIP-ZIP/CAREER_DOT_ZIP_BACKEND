from rest_framework import serializers
from apps.interview.models import InterviewAnswer
from .models import Evaluation, AnswerWeaknessTag, AnswerStrengthTag


class EvaluationCreateSerializer(serializers.Serializer):
  answer_id = serializers.UUIDField()
  answer_sufficiency = serializers.JSONField(required=False)

  def validate_answer_id(self, value):
    request = self.context.get('request')
    try:
      answer = InterviewAnswer.objects.select_related('session').get(id=value)
    except InterviewAnswer.DoesNotExist:
      raise serializers.ValidationError('Answer not found.')

    if request and answer.session.user_id != request.user.id:
      raise serializers.ValidationError('Answer not found.')

    return answer

  def validate(self, attrs):
    answer = attrs.get('answer_id')
    if answer and Evaluation.objects.filter(answer=answer).exists():
      raise serializers.ValidationError('Evaluation for this answer already exists.')
    return attrs


class EvaluationSerializer(serializers.ModelSerializer):
  evaluation_id = serializers.SerializerMethodField()
  answer_id = serializers.SerializerMethodField()

  class Meta:
    model = Evaluation
    fields = (
        'evaluation_id',
        'answer_id',
        'bei_score',
        'cbi_score',
        'filler_words',
        'sbert_db_similarity',
        'sbert_readme_similarity',
        'llm_concept_score',
        'final_tech_score',
        'score_detail',
        'evaluated_at',
    )

  def get_evaluation_id(self, obj):
    return str(obj.id)

  def get_answer_id(self, obj):
    return str(obj.answer.id)


class AnswerWeaknessTagSerializer(serializers.ModelSerializer):
  id = serializers.SerializerMethodField()
  tag_name = serializers.CharField(source='weakness_tag.tag_name')

  class Meta:
    model = AnswerWeaknessTag
    fields = (
        'id',
        'tag_name',
        'reason',
        'priority_rank',
        'is_selected_for_followup',
        'used_for',
        'followup_question_id',
    )

  def get_id(self, obj):
    return str(obj.id)


class AnswerStrengthTagSerializer(serializers.ModelSerializer):
  id = serializers.SerializerMethodField()
  tag_name = serializers.CharField(source='strength_tag.tag_name')

  class Meta:
    model = AnswerStrengthTag
    fields = ('id', 'tag_name', 'reason', 'priority_rank', 'trigger_signal_log')

  def get_id(self, obj):
    return str(obj.id)
