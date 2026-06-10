from rest_framework import serializers

from apps.interview.models import InterviewSession
from apps.report.models import FinalReport


class InterviewHistoryQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, default=10, min_value=1)
    status = serializers.ChoiceField(
        choices=InterviewSession.STATUS_CHOICES,
        required=False,
    )


class InterviewHistorySerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source='id', read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    answer_count = serializers.IntegerField(read_only=True)
    has_report = serializers.SerializerMethodField()
    report_id = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSession
        fields = (
            'session_id',
            'interview_type',
            'persona',
            'status',
            'question_count',
            'answer_count',
            'has_report',
            'report_id',
            'overall_score',
            'started_at',
            'ended_at',
            'created_at',
        )

    def get_report(self, obj):
        try:
            return obj.final_report
        except FinalReport.DoesNotExist:
            return None

    def get_has_report(self, obj):
        return self.get_report(obj) is not None

    def get_report_id(self, obj):
        report = self.get_report(obj)
        return str(report.id) if report else None

    def get_overall_score(self, obj):
        report = self.get_report(obj)
        if not report:
            return None
        return report.overall_score
