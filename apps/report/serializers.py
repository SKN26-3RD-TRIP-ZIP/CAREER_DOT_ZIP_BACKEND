from django.utils import timezone
from rest_framework import serializers
from .models import FinalReport, RoadmapItem


# 모델 status → 프론트 폴링 계약 값 매핑.
# done 은 기존 프론트가 기대하는 'completed' 로 유지(하위호환).
_FRONTEND_STATUS = {
    FinalReport.STATUS_DONE: 'completed',
    FinalReport.STATUS_PROCESSING: 'processing',
    FinalReport.STATUS_PENDING: 'processing',
    FinalReport.STATUS_FAILED: 'failed',
}


def frontend_status(obj):
    return _FRONTEND_STATUS.get(obj.status, 'completed')


# 공유 링크(AllowAny)로 외부에 노출해도 안전한 evaluation_metadata 하위 필드.
# session_id/calculated_at 등 내부 식별자는 제외한다.
_SHARED_METADATA_FIELDS = (
    "persona_type", "interview_mode", "interview_type",
    "question_count", "answer_count", "evaluated_answer_count",
    "unscored_answer_count", "summary_text",
)


def build_shared_summary(summary):
    """공유 링크용 summary 투영(projection)(#4).

    원본 답변 텍스트는 summary에 저장되지 않지만, score_detail(질문별 점수·
    상세 통계·발화 진단)은 세밀한 개인 수행 데이터이므로 공개 범위에서 제외한다.
    헤드라인(총점/지표/페르소나 피드백)과 강·약점 태그, 요약문만 내보낸다.
    """
    summary = summary or {}
    metadata = summary.get("evaluation_metadata", {}) or {}
    return {
        "evaluation_metadata": {
            key: metadata[key] for key in _SHARED_METADATA_FIELDS if key in metadata
        },
        "score_summary": summary.get("score_summary", {}),
        "dynamically_triggered_tags": summary.get("dynamically_triggered_tags", {}),
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

    class Meta:
        model = FinalReport
        fields = (
            'report_id', 'session_id', 'interview_type', 'persona',
            'overall_score', 'status', 'error_code', 'summary', 'generated_at',
        )

    def get_report_id(self, obj): return str(obj.id)
    def get_session_id(self, obj): return str(obj.session.id)
    def get_interview_type(self, obj): return obj.session.interview_type
    def get_persona(self, obj): return obj.session.persona
    def get_overall_score(self, obj): return obj.overall_score
    def get_status(self, obj): return frontend_status(obj)


class FinalReportListSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    interview_type = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()
    summary_text = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id', 'session_id', 'interview_type', 'persona',
            'overall_score', 'summary_text', 'generated_at',
        )

    def get_report_id(self, obj): return str(obj.id)
    def get_session_id(self, obj): return str(obj.session.id)
    def get_interview_type(self, obj): return obj.session.interview_type
    def get_persona(self, obj): return obj.session.persona
    def get_overall_score(self, obj): return obj.overall_score
    def get_summary_text(self, obj):
        metadata = (obj.summary or {}).get('evaluation_metadata', {})
        return metadata.get('summary_text', '')


class FinalReportSessionSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()

    error_code = serializers.CharField(read_only=True)

    class Meta:
        model = FinalReport
        fields = ('report_id', 'session_id', 'status', 'error_code', 'overall_score', 'summary', 'generated_at')

    def get_report_id(self, obj): return str(obj.id)
    def get_session_id(self, obj): return str(obj.session.id)
    def get_status(self, obj): return frontend_status(obj)
    def get_overall_score(self, obj): return obj.overall_score
