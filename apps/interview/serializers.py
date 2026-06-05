from rest_framework import serializers

from apps.common.choices import ANSWER_SOURCE_CHOICES
from apps.input.models import JobDescription, ResumeMaster, CoverLetter
from .models import InterviewSession, InterviewQuestion, InterviewAnswer


class InterviewSessionCreateSerializer(serializers.ModelSerializer):
    jd_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    resume_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    cover_letter_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = InterviewSession
        fields = (
            'jd_id',
            'resume_id',
            'cover_letter_id',
            'interview_type',
            'persona',
            'total_question_count',
        )
        extra_kwargs = {
            'total_question_count': {'required': False},
        }

    def validate_jd_id(self, value):
        if value is None:
            return None
        try:
            return JobDescription.objects.get(id=value, user=self.context['request'].user)
        except JobDescription.DoesNotExist:
            raise serializers.ValidationError('Job description not found.')

    def validate_resume_id(self, value):
        if value is None:
            return None
        try:
            return ResumeMaster.objects.get(id=value, user=self.context['request'].user)
        except ResumeMaster.DoesNotExist:
            raise serializers.ValidationError('Resume not found.')

    def validate_cover_letter_id(self, value):
        if value is None:
            return None
        try:
            return CoverLetter.objects.get(id=value, user=self.context['request'].user)
        except CoverLetter.DoesNotExist:
            raise serializers.ValidationError('Cover letter not found.')

    def create(self, validated_data):
        jd = validated_data.pop('jd_id', None)
        resume = validated_data.pop('resume_id', None)
        cover_letter = validated_data.pop('cover_letter_id', None)

        if jd is not None:
            validated_data['jd'] = jd
        if resume is not None:
            validated_data['resume'] = resume
        if cover_letter is not None:
            validated_data['cover_letter'] = cover_letter

        return InterviewSession.objects.create(**validated_data)


class InterviewSessionListSerializer(serializers.ModelSerializer):
    session_id = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSession
        fields = ('session_id', 'interview_type', 'persona', 'status', 'created_at')

    def get_session_id(self, obj):
        return str(obj.id)


class InterviewSessionDetailSerializer(serializers.ModelSerializer):
    session_id = serializers.SerializerMethodField()
    jd_id = serializers.SerializerMethodField()
    resume_id = serializers.SerializerMethodField()
    cover_letter_id = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSession
        fields = (
            'session_id',
            'jd_id',
            'resume_id',
            'cover_letter_id',
            'interview_type',
            'persona',
            'status',
            'total_question_count',
            'current_question_index',
            'started_at',
            'ended_at',
            'created_at',
            'updated_at',
        )

    def get_session_id(self, obj):
        return str(obj.id)

    def get_jd_id(self, obj):
        return str(obj.jd.id) if obj.jd else None

    def get_resume_id(self, obj):
        return str(obj.resume.id) if obj.resume else None

    def get_cover_letter_id(self, obj):
        return str(obj.cover_letter.id) if obj.cover_letter else None


class InterviewSessionStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewSession
        fields = ('status',)


class InterviewQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.SerializerMethodField()

    class Meta:
        model = InterviewQuestion
        fields = (
            'question_id',
            'order_index',
            'question_type',
            'question_text',
            'source_type',
            'source_reference',
            'created_at',
        )

    def get_question_id(self, obj):
        return str(obj.id)


class InterviewAnswerCreateSerializer(serializers.Serializer):
    answer_text = serializers.CharField()
    answer_source = serializers.ChoiceField(choices=ANSWER_SOURCE_CHOICES, required=False, default='text')

    def validate(self, attrs):
        return attrs


class InterviewAnswerSerializer(serializers.ModelSerializer):
    answer_id = serializers.SerializerMethodField()
    question_id = serializers.SerializerMethodField()

    class Meta:
        model = InterviewAnswer
        fields = ('answer_id', 'question_id', 'answer_text', 'answer_source', 'created_at')

    def get_answer_id(self, obj):
        return str(obj.id)

    def get_question_id(self, obj):
        return str(obj.question.id)


class FollowUpQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.SerializerMethodField()
    parent_question_id = serializers.SerializerMethodField()
    answer_id = serializers.SerializerMethodField()

    class Meta:
        model = InterviewQuestion
        fields = (
            'question_id',
            'parent_question_id',
            'answer_id',
            'order_index',
            'question_type',
            'question_text',
            'source_type',
            'source_reference',
            'created_at',
        )

    def get_question_id(self, obj):
        return str(obj.id)

    def get_parent_question_id(self, obj):
        return str(obj.parent_question.id) if obj.parent_question else None

    def get_answer_id(self, obj):
        return str(obj.source_answer.id) if obj.source_answer else None

