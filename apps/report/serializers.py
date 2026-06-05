from rest_framework import serializers
from .models import FinalReport


class FinalReportSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    interview_type = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'interview_type',
            'persona',
            'overall_score',
            'summary',
            'strengths',
            'weaknesses',
            'recommendations',
            'question_count',
            'answer_count',
            'evaluated_answer_count',
            'created_at',
            'updated_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_interview_type(self, obj):
        return obj.session.interview_type

    def get_persona(self, obj):
        return obj.session.persona


class FinalReportListSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    interview_type = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'interview_type',
            'persona',
            'overall_score',
            'summary',
            'created_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_interview_type(self, obj):
        return obj.session.interview_type

    def get_persona(self, obj):
        return obj.session.persona
