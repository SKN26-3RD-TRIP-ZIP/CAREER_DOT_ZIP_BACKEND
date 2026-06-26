from django.utils import timezone
from rest_framework import serializers

from .models import ActionPlan, FinalReport, RoadmapItem


_FRONTEND_STATUS = {
    FinalReport.STATUS_DONE: 'completed',
    FinalReport.STATUS_PROCESSING: 'processing',
    FinalReport.STATUS_PENDING: 'processing',
    FinalReport.STATUS_FAILED: 'failed',
}


def frontend_status(obj):
    return _FRONTEND_STATUS.get(obj.status, 'completed')


_SHARED_METADATA_FIELDS = (
    'persona_type',
    'interview_mode',
    'interview_type',
    'question_count',
    'answer_count',
    'evaluated_answer_count',
    'unscored_answer_count',
    'summary_text',
)


def build_shared_summary(summary):
    summary = summary or {}
    metadata = summary.get('evaluation_metadata', {}) or {}
    return {
        'evaluation_metadata': {
            key: metadata[key] for key in _SHARED_METADATA_FIELDS if key in metadata
        },
        'score_summary': summary.get('score_summary', {}),
        'dynamically_triggered_tags': summary.get('dynamically_triggered_tags', {}),
    }


class RoadmapItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='item_id')
    days_elapsed = serializers.SerializerMethodField()

    class Meta:
        model = RoadmapItem
        fields = ('id', 'title', 'description', 'days_elapsed', 'priority')

    def get_days_elapsed(self, obj):
        delta = timezone.now() - obj.created_at
        return delta.days


class RoadmapResponseSerializer(serializers.Serializer):
    week_priority_text = serializers.CharField()
    target_delta_label = serializers.CharField()
    practice_question = serializers.CharField()
    items = RoadmapItemSerializer(many=True)


class FinalReportSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    interview_type = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    error_code = serializers.CharField(read_only=True)
    score_status = serializers.SerializerMethodField()
    evaluation_status = serializers.SerializerMethodField()
    is_mock = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'interview_type',
            'persona',
            'overall_score',
            'status',
            'error_code',
            'score_status',
            'evaluation_status',
            'is_mock',
            'summary',
            'generated_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_interview_type(self, obj):
        return obj.session.interview_type

    def get_persona(self, obj):
        return obj.session.persona

    def get_overall_score(self, obj):
        return obj.overall_score

    def get_status(self, obj):
        return frontend_status(obj)

    def get_score_status(self, obj):
        return obj.score_status

    def get_evaluation_status(self, obj):
        return obj.evaluation_status

    def get_is_mock(self, obj):
        return obj.is_mock


class FinalReportListSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    interview_type = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    error_code = serializers.CharField(read_only=True)
    score_status = serializers.SerializerMethodField()
    evaluation_status = serializers.SerializerMethodField()
    is_mock = serializers.SerializerMethodField()
    summary_text = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'interview_type',
            'persona',
            'overall_score',
            'status',
            'error_code',
            'score_status',
            'evaluation_status',
            'is_mock',
            'summary_text',
            'generated_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_interview_type(self, obj):
        return obj.session.interview_type

    def get_persona(self, obj):
        return obj.session.persona

    def get_overall_score(self, obj):
        return obj.overall_score

    def get_status(self, obj):
        return frontend_status(obj)

    def get_score_status(self, obj):
        return obj.score_status

    def get_evaluation_status(self, obj):
        return obj.evaluation_status

    def get_is_mock(self, obj):
        return obj.is_mock

    def get_summary_text(self, obj):
        metadata = (obj.summary or {}).get('evaluation_metadata', {})
        return metadata.get('summary_text', '')


class FinalReportSessionSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    error_code = serializers.CharField(read_only=True)
    overall_score = serializers.SerializerMethodField()
    score_status = serializers.SerializerMethodField()
    evaluation_status = serializers.SerializerMethodField()
    is_mock = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'status',
            'error_code',
            'overall_score',
            'score_status',
            'evaluation_status',
            'is_mock',
            'summary',
            'generated_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_status(self, obj):
        return frontend_status(obj)

    def get_overall_score(self, obj):
        return obj.overall_score

    def get_score_status(self, obj):
        return obj.score_status

    def get_evaluation_status(self, obj):
        return obj.evaluation_status

    def get_is_mock(self, obj):
        return obj.is_mock


class ActionPlanSerializer(serializers.ModelSerializer):
    action_plan_id = serializers.UUIDField(source='id', read_only=True)
    report_id = serializers.UUIDField(source='report.id', read_only=True)
    session_id = serializers.UUIDField(source='report.session.id', read_only=True)

    class Meta:
        model = ActionPlan
        fields = (
            'action_plan_id',
            'report_id',
            'session_id',
            'title',
            'description',
            'status',
            'source_tag',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')


class ActionPlanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionPlan
        fields = ('title', 'description', 'source_tag')


class ActionPlanPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionPlan
        fields = ('title', 'description', 'status', 'source_tag')
        extra_kwargs = {
            'title': {'required': False},
            'description': {'required': False},
            'status': {'required': False},
            'source_tag': {'required': False},
        }
