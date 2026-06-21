from django.utils import timezone
from rest_framework import serializers
from .models import FinalReport, RoadmapItem


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

    class Meta:
        model = FinalReport
        fields = (
            'report_id', 'session_id', 'interview_type', 'persona',
            'overall_score', 'summary', 'generated_at',
        )

    def get_report_id(self, obj): return str(obj.id)
    def get_session_id(self, obj): return str(obj.session.id)
    def get_interview_type(self, obj): return obj.session.interview_type
    def get_persona(self, obj): return obj.session.persona
    def get_overall_score(self, obj): return obj.overall_score


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

    class Meta:
        model = FinalReport
        fields = ('report_id', 'session_id', 'status', 'overall_score', 'summary', 'generated_at')

    def get_report_id(self, obj): return str(obj.id)
    def get_session_id(self, obj): return str(obj.session.id)
    def get_status(self, obj): return 'completed'
    def get_overall_score(self, obj): return obj.overall_score
