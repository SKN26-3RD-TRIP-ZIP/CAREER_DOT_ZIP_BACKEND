from rest_framework import serializers
from .models import ActionPlan, FinalReport


class FinalReportSerializer(serializers.ModelSerializer):
  report_id = serializers.SerializerMethodField()
  session_id = serializers.SerializerMethodField()
  interview_type = serializers.SerializerMethodField()
  persona = serializers.SerializerMethodField()
  overall_score = serializers.SerializerMethodField()
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
    return 'completed'

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
