from rest_framework import serializers

from apps.input.models import CoverLetter, JobDescription, ProjectExperience, ResumeMaster
from apps.question_bank.models import QuestionBankItem
from .models import InterviewAnswer, InterviewQuestion, InterviewSession


PERSONA_INPUT_MAP = {
    'coach': 'coach',
    'practical': 'practical',
    'verify': 'verifier',
    'verifier': 'verifier',
    'pressure': 'pressure',
}
PERSONA_OUTPUT_MAP = {
    'coach': 'coach',
    'practical': 'practical',
    'verifier': 'verify',
    'pressure': 'pressure',
}
STATUS_INPUT_MAP = {
    'in_progress': 'in_progress',
    'completed': 'completed',
    'canceled': 'cancelled',
    'failed': 'failed',
}
STATUS_OUTPUT_MAP = {
    'created': 'ready',
    'cancelled': 'canceled',
}


class MVPSessionCreateSerializer(serializers.Serializer):
    jd_id = serializers.UUIDField()
    resume_id = serializers.UUIDField(required=False, allow_null=True)
    cover_letter_id = serializers.UUIDField(required=False, allow_null=True)
    # persona_type: 프론트 필드명. persona도 별칭으로 허용
    persona_type = serializers.ChoiceField(choices=PERSONA_INPUT_MAP, required=False)
    persona = serializers.ChoiceField(choices=PERSONA_INPUT_MAP, required=False)
    interview_mode = serializers.ChoiceField(choices=('text', 'voice'), required=False, default='voice')
    # interview_type: 프론트에서 전송하는 기존 필드(무시하지 않고 저장)
    interview_type = serializers.ChoiceField(
        choices=('technical', 'personality', 'comprehensive'),
        required=False,
        default='comprehensive',
    )
    total_question_count = serializers.IntegerField(required=False, min_value=1, max_value=20)

    def validate(self, attrs):
        user = self.context['request'].user
        attrs['jd'] = self._owned_object(JobDescription, attrs.pop('jd_id'), user, 'JD')

        resume_id = attrs.pop('resume_id', None)
        attrs['resume'] = (
            self._owned_object(ResumeMaster, resume_id, user, 'Resume')
            if resume_id
            else None
        )

        cover_letter_id = attrs.pop('cover_letter_id', None)
        attrs['cover_letter'] = (
            self._owned_object(CoverLetter, cover_letter_id, user, 'Cover letter')
            if cover_letter_id
            else None
        )

        # persona_type 우선, 없으면 persona 필드 사용
        raw_persona = attrs.pop('persona_type', None) or attrs.pop('persona', None)
        if not raw_persona:
            raise serializers.ValidationError({'persona_type': 'persona_type or persona is required.'})
        attrs['persona'] = PERSONA_INPUT_MAP[raw_persona]

        return attrs

    @staticmethod
    def _owned_object(model, object_id, user, label):
        try:
            return model.objects.get(id=object_id, user=user)
        except model.DoesNotExist:
            raise serializers.ValidationError({f'{label.lower().replace(" ", "_")}_id': f'{label} not found.'})

    def create(self, validated_data):
        total_question_count = validated_data.pop('total_question_count', 5)
        return InterviewSession.objects.create(
            user=self.context['request'].user,
            status='created',
            total_question_count=total_question_count,
            **validated_data,
        )


class MVPSessionStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=STATUS_INPUT_MAP)


class MVPQuestionGenerateSerializer(serializers.Serializer):
    jd_id = serializers.UUIDField(required=False)
    resume_id = serializers.UUIDField(required=False)
    cover_letter_id = serializers.UUIDField(required=False, allow_null=True)
    project_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    question_count = serializers.IntegerField(required=False, default=3, min_value=1, max_value=20)

    def validate(self, attrs):
        session = self.context['session']
        self._validate_session_reference(attrs, 'jd_id', session.jd_id)
        self._validate_session_reference(attrs, 'resume_id', session.resume_id)
        self._validate_session_reference(attrs, 'cover_letter_id', session.cover_letter_id)

        project_ids = attrs.get('project_ids', [])
        owned_count = ProjectExperience.objects.filter(
            id__in=project_ids,
            user=self.context['request'].user,
        ).count()
        if owned_count != len(set(project_ids)):
            raise serializers.ValidationError({'project_ids': 'One or more projects were not found.'})
        return attrs

    @staticmethod
    def _validate_session_reference(attrs, field_name, session_value):
        if field_name in attrs and attrs[field_name] != session_value:
            raise serializers.ValidationError(
                {field_name: 'The resource does not match this session.'}
            )


class MVPQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.UUIDField(source='id', read_only=True)
    question_type = serializers.SerializerMethodField()
    difficulty = serializers.SerializerMethodField()
    parent_question_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = InterviewQuestion
        fields = (
            'question_id',
            'question_text',
            'question_type',
            'difficulty',
            'order_index',
            'parent_question_id',
        )

    def _bank_item(self, obj):
        if obj.source_type != 'question_bank' or not obj.source_reference:
            return None
        try:
            _, item_id = obj.source_reference.split(':', 1)
            return QuestionBankItem.objects.filter(id=item_id).first()
        except (ValueError, TypeError):
            return None

    def get_question_type(self, obj):
        bank_item = self._bank_item(obj)
        if bank_item:
            return bank_item.question_type
        return {
            'technical': 'technical',
            'personality': 'personality',
        }.get(obj.session.interview_type, 'job')

    def get_difficulty(self, obj):
        bank_item = self._bank_item(obj)
        return bank_item.difficulty if bank_item else 'medium'


class MVPAnswerCreateSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    question_id = serializers.UUIDField()
    answer_text = serializers.CharField(allow_blank=False, trim_whitespace=True)
    speech_duration = serializers.FloatField(required=False, min_value=0)


class MVPSTTResultUpdateSerializer(serializers.ModelSerializer):
    stt_text = serializers.CharField(allow_blank=False, trim_whitespace=True)
    audio_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    speech_duration = serializers.FloatField(required=False, min_value=0)
    total_pause_duration = serializers.FloatField(required=False, min_value=0)
    long_pause_count = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = InterviewAnswer
        fields = (
            'stt_text',
            'audio_url',
            'speech_duration',
            'total_pause_duration',
            'long_pause_count',
        )


class MVPFollowupQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.UUIDField(source='id', read_only=True)
    parent_question_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = InterviewQuestion
        fields = ('question_id', 'question_text', 'parent_question_id')


def serialize_mvp_session(session, include_created_at=False, prompt_version_id=None):
    data = {
        'session_id': str(session.id),
        'status': STATUS_OUTPUT_MAP.get(session.status, session.status),
        'persona_type': PERSONA_OUTPUT_MAP.get(session.persona, session.persona),
        'interview_mode': session.interview_mode,
    }
    if include_created_at:
        data['prompt_version_id'] = prompt_version_id
        data['created_at'] = session.created_at
    else:
        data['started_at'] = session.started_at
        data['ended_at'] = session.ended_at
    return data
