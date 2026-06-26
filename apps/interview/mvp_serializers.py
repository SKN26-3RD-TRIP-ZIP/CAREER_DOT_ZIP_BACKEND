"""Serializers for the active flat MVP interview API.

This contract intentionally uses compact frontend payloads and status/persona
aliases. It remains separate from serializers.py until a canonical API is
selected.
"""

from rest_framework import serializers

from apps.analysis.models import AnalysisSession, JdAnalysis
from apps.input.models import CoverLetter, JobDescription, ProjectExperience, ResumeMaster
from apps.prompt.models import PromptVersion
from apps.prompt.services import normalize_prompt_persona_type
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
    jd_id = serializers.UUIDField(required=False)
    resume_id = serializers.UUIDField(required=False, allow_null=True)
    cover_letter_id = serializers.UUIDField(required=False, allow_null=True)
    analysis_session_id = serializers.IntegerField(required=False)
    jd_analysis_id = serializers.UUIDField(required=False)
    # persona_type: 프론트 필드명. persona도 별칭으로 허용
    persona_type = serializers.ChoiceField(choices=PERSONA_INPUT_MAP, required=False)
    persona = serializers.ChoiceField(choices=PERSONA_INPUT_MAP, required=False)
    # interview_mode controls text/voice I/O, not question content.
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
        jd_analysis = self._resolve_jd_analysis(
            user=user,
            jd_analysis_id=attrs.pop('jd_analysis_id', None),
            analysis_session_id=attrs.pop('analysis_session_id', None),
        )

        jd_id = attrs.pop('jd_id', None)
        if jd_id:
            attrs['jd'] = self._owned_object(JobDescription, jd_id, user, 'JD')
        elif jd_analysis:
            attrs['jd'] = jd_analysis.jd
        else:
            raise serializers.ValidationError(
                {'jd_id': 'This field is required unless jd_analysis_id or analysis_session_id is provided.'}
            )

        resume_id = attrs.pop('resume_id', None)
        attrs['resume'] = (
            self._owned_object(ResumeMaster, resume_id, user, 'Resume')
            if resume_id
            else jd_analysis.resume if jd_analysis else None
        )

        cover_letter_id = attrs.pop('cover_letter_id', None)
        attrs['cover_letter'] = (
            self._owned_object(CoverLetter, cover_letter_id, user, 'Cover letter')
            if cover_letter_id
            else jd_analysis.cover_letter if jd_analysis else None
        )

        if jd_analysis:
            self._validate_analysis_resources(attrs, jd_analysis)

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

    @staticmethod
    def _resolve_jd_analysis(*, user, jd_analysis_id=None, analysis_session_id=None):
        jd_analysis = None

        if jd_analysis_id:
            try:
                jd_analysis = JdAnalysis.objects.select_related(
                    'jd',
                    'resume',
                    'cover_letter',
                ).get(id=jd_analysis_id, user=user)
            except JdAnalysis.DoesNotExist:
                raise serializers.ValidationError({'jd_analysis_id': 'JD analysis not found.'})

        if analysis_session_id:
            try:
                analysis_session = AnalysisSession.objects.select_related(
                    'jd_analysis__jd',
                    'jd_analysis__resume',
                    'jd_analysis__cover_letter',
                ).get(id=analysis_session_id, user=user)
            except AnalysisSession.DoesNotExist:
                raise serializers.ValidationError({'analysis_session_id': 'Analysis session not found.'})

            if not analysis_session.jd_analysis_id:
                raise serializers.ValidationError(
                    {'analysis_session_id': 'Analysis session has no completed result.'}
                )
            if jd_analysis and jd_analysis.id != analysis_session.jd_analysis_id:
                raise serializers.ValidationError(
                    {'jd_analysis_id': 'JD analysis does not match analysis_session_id.'}
                )
            jd_analysis = analysis_session.jd_analysis

        return jd_analysis

    @staticmethod
    def _validate_analysis_resources(attrs, jd_analysis):
        if attrs['jd'].id != jd_analysis.jd_id:
            raise serializers.ValidationError({'jd_id': 'JD does not match the analysis result.'})
        if attrs['resume'] and attrs['resume'].id != jd_analysis.resume_id:
            raise serializers.ValidationError({'resume_id': 'Resume does not match the analysis result.'})
        if attrs['cover_letter'] and attrs['cover_letter'].id != jd_analysis.cover_letter_id:
            raise serializers.ValidationError(
                {'cover_letter_id': 'Cover letter does not match the analysis result.'}
            )

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


class PracticeSessionCreateSerializer(serializers.Serializer):
    question_count = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=10,
    )
    persona_type = serializers.ChoiceField(
        choices=PERSONA_INPUT_MAP,
        required=False,
    )
    interview_mode = serializers.ChoiceField(
        choices=('text', 'voice'),
        required=False,
    )

    def validate_persona_type(self, value):
        return PERSONA_INPUT_MAP[value]


class MVPQuestionGenerateSerializer(serializers.Serializer):
    jd_id = serializers.UUIDField(required=False)
    resume_id = serializers.UUIDField(required=False)
    cover_letter_id = serializers.UUIDField(required=False, allow_null=True)
    analysis_session_id = serializers.IntegerField(required=False)
    jd_analysis_id = serializers.UUIDField(required=False)
    project_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    question_count = serializers.IntegerField(required=False, default=3, min_value=1, max_value=20)
    prompt_version_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        session = self.context['session']
        self._validate_session_reference(attrs, 'jd_id', session.jd_id)
        self._validate_session_reference(attrs, 'resume_id', session.resume_id)
        self._validate_session_reference(attrs, 'cover_letter_id', session.cover_letter_id)
        self._validate_jd_analysis_reference(attrs)

        project_ids = attrs.get('project_ids', [])
        owned_count = ProjectExperience.objects.filter(
            id__in=project_ids,
            user=self.context['request'].user,
        ).count()
        if owned_count != len(set(project_ids)):
            raise serializers.ValidationError({'project_ids': 'One or more projects were not found.'})

        self._validate_prompt_version(attrs)
        return attrs

    def _validate_prompt_version(self, attrs):
        prompt_version_id = attrs.get('prompt_version_id')
        if not prompt_version_id:
            return

        user = self.context['request'].user
        if not (
            getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) == 'admin'
        ):
            raise serializers.ValidationError(
                {'prompt_version_id': 'Only admins can select a prompt version.'}
            )

        session = self.context['session']
        version = (
            PromptVersion.objects.filter(id=prompt_version_id)
            .select_related('template__persona_config')
            .first()
        )
        if version is None or not version.template.is_active:
            raise serializers.ValidationError({'prompt_version_id': 'Prompt version was not found.'})
        if version.template.prompt_type != 'question_generation':
            raise serializers.ValidationError(
                {'prompt_version_id': 'Prompt version must be for question generation.'}
            )
        expected_persona = normalize_prompt_persona_type(
            PERSONA_OUTPUT_MAP.get(session.persona, session.persona)
        )
        version_persona = normalize_prompt_persona_type(
            version.template.persona_config.persona_type
        )
        if version_persona != expected_persona:
            raise serializers.ValidationError(
                {'prompt_version_id': 'Prompt version persona does not match this session.'}
            )

    @staticmethod
    def _validate_session_reference(attrs, field_name, session_value):
        if field_name in attrs and attrs[field_name] != session_value:
            raise serializers.ValidationError(
                {field_name: 'The resource does not match this session.'}
            )

    def _validate_jd_analysis_reference(self, attrs):
        jd_analysis = MVPSessionCreateSerializer._resolve_jd_analysis(
            user=self.context['request'].user,
            jd_analysis_id=attrs.get('jd_analysis_id'),
            analysis_session_id=attrs.get('analysis_session_id'),
        )
        if not jd_analysis:
            return

        session = self.context['session']
        if session.jd_id and session.jd_id != jd_analysis.jd_id:
            raise serializers.ValidationError({'jd_analysis_id': 'JD analysis does not match this session.'})
        if session.resume_id and session.resume_id != jd_analysis.resume_id:
            raise serializers.ValidationError({'jd_analysis_id': 'JD analysis does not match this session.'})
        if session.cover_letter_id and session.cover_letter_id != jd_analysis.cover_letter_id:
            raise serializers.ValidationError({'jd_analysis_id': 'JD analysis does not match this session.'})

        attrs['jd_analysis'] = jd_analysis


class MVPQuestionSerializer(serializers.ModelSerializer):
    # question_type is the flow role (main/follow_up); question_category is
    # the content class (technical/personality/general).
    question_id = serializers.UUIDField(source='id', read_only=True)
    question_category = serializers.CharField(read_only=True)
    difficulty = serializers.SerializerMethodField()
    parent_question_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = InterviewQuestion
        fields = (
            'question_id',
            'question_text',
            'question_type',
            'question_category',
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

    def get_difficulty(self, obj):
        bank_item = self._bank_item(obj)
        return bank_item.difficulty if bank_item else 'medium'


class MVPAnswerCreateSerializer(serializers.Serializer):
    # 음성/텍스트 답변 생성 API에서 공통으로 받는 최소 입력값만 검증한다.
    session_id = serializers.UUIDField()
    question_id = serializers.UUIDField()
    answer_text = serializers.CharField(allow_blank=False, trim_whitespace=True)
    speech_duration = serializers.FloatField(required=False, min_value=0)


class MVPSTTResultUpdateSerializer(serializers.ModelSerializer):
    # STT 후처리 patch는 텍스트와 음성 분석 지표만 답변 레코드에 덧붙인다.
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
    question_category = serializers.CharField(read_only=True)

    class Meta:
        model = InterviewQuestion
        fields = (
            'question_id',
            'question_text',
            'question_type',
            'question_category',
            'parent_question_id',
        )


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
