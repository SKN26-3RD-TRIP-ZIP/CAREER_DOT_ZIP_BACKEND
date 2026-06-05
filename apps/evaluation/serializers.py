from rest_framework import serializers
from apps.interview.models import InterviewAnswer
from .models import Evaluation, WeaknessTag, StrengthTag, AnswerWeaknessTag, AnswerStrengthTag


class EvaluationCreateSerializer(serializers.Serializer):
    answer_id = serializers.UUIDField()
    bei_score = serializers.JSONField(required=False, allow_null=True)
    cbi_score = serializers.JSONField(required=False, allow_null=True)
    filler_words = serializers.JSONField(required=False, allow_null=True)
    sbert_db_similarity = serializers.FloatField(required=False, allow_null=True)
    sbert_readme_similarity = serializers.FloatField(required=False, allow_null=True)
    llm_concept_score = serializers.IntegerField(required=False, allow_null=True)
    final_tech_score = serializers.IntegerField(required=False, allow_null=True)
    score_detail = serializers.JSONField(required=False, allow_null=True)

    def validate_answer_id(self, value):
        try:
            answer = InterviewAnswer.objects.get(id=value)
            return answer
        except InterviewAnswer.DoesNotExist:
            raise serializers.ValidationError('Answer not found.')

    def validate(self, attrs):
        answer = attrs.get('answer_id')
        if answer and hasattr(answer, 'evaluation') and answer.evaluation:
            raise serializers.ValidationError('Evaluation for this answer already exists.')
        return attrs

    def create(self, validated_data):
        answer = validated_data.pop('answer_id')
        evaluation = Evaluation.objects.create(
            answer=answer,
            bei_score=validated_data.get('bei_score', {}),
            cbi_score=validated_data.get('cbi_score', {}),
            filler_words=validated_data.get('filler_words', {}),
            sbert_db_similarity=validated_data.get('sbert_db_similarity'),
            sbert_readme_similarity=validated_data.get('sbert_readme_similarity'),
            llm_concept_score=validated_data.get('llm_concept_score'),
            final_tech_score=validated_data.get('final_tech_score'),
            score_detail=validated_data.get('score_detail', {}),
        )
        return evaluation


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


class WeaknessTagDetailSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    tag_name = serializers.CharField()
    reason = serializers.CharField()
    priority_rank = serializers.IntegerField()
    is_selected_for_followup = serializers.BooleanField()
    used_for = serializers.CharField()
    followup_question_id = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_followup_question_id(self, obj):
        return str(obj.followup_question_id) if obj.followup_question_id else None


class AnswerWeaknessTagSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    tag_name = serializers.CharField(source='weakness_tag.tag_name')

    class Meta:
        model = AnswerWeaknessTag
        fields = ('id', 'tag_name', 'reason', 'priority_rank', 'is_selected_for_followup', 'used_for', 'followup_question_id')

    def get_id(self, obj):
        return str(obj.id)


class StrengthTagDetailSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    tag_name = serializers.CharField()
    reason = serializers.CharField()
    priority_rank = serializers.IntegerField()
    trigger_signal_log = serializers.CharField()

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
