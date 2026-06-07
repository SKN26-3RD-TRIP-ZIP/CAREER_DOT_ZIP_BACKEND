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


class FinalReportSessionSerializer(serializers.ModelSerializer):
    report_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    generated_at = serializers.SerializerMethodField()

    class Meta:
        model = FinalReport
        fields = (
            'report_id',
            'session_id',
            'status',
            'summary',
            'generated_at',
        )

    def get_report_id(self, obj):
        return str(obj.id)

    def get_session_id(self, obj):
        return str(obj.session.id)

    def get_status(self, obj):
        return 'completed'

    def get_generated_at(self, obj):
        return obj.created_at

    def get_summary(self, obj):
        raw_data = obj.raw_data or {}
        supported_scores = raw_data.get('supported_scores', {})

        final_tech_scores = supported_scores.get('final_tech_scores', [])
        llm_concept_scores = supported_scores.get('llm_concept_scores', [])

        tech_avg = round(sum(final_tech_scores) / len(final_tech_scores), 1) if final_tech_scores else 0
        llm_avg = round(sum(llm_concept_scores) / len(llm_concept_scores), 1) if llm_concept_scores else 0

        return {
            'evaluation_metadata': {
                'session_id': str(obj.session.id),
                'persona_type': obj.session.persona,
                'interview_mode': obj.session.interview_mode,
                'question_count': obj.question_count,
                'evaluated_at': obj.updated_at,
            },
            'score_summary': {
                'overall_score': obj.overall_score,
                'bei_avg': raw_data.get('bei_avg', 0),
                'cbi_avg': raw_data.get('cbi_avg', 0),
                'tech_avg': tech_avg or llm_avg,
            },
            'score_detail': {
                'strength': ', '.join(obj.strengths) if isinstance(obj.strengths, list) else obj.strengths,
                'weakness': ', '.join(obj.weaknesses) if isinstance(obj.weaknesses, list) else obj.weaknesses,
                'improvement': obj.recommendations,
            },
            'dynamically_triggered_tags': {
                'weakness_tags': raw_data.get('weakness_tags', []),
                'strength_tags': raw_data.get('strength_tags', []),
            },
        }
