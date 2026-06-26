import uuid
from django.db import models


class FinalReport(models.Model):
    """Session-level report. Stored per design doc as feedback_reports (summary JSONB)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        'interview.InterviewSession',
        on_delete=models.CASCADE,
        related_name='final_report',
    )
    summary = models.JSONField(default=dict)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feedback_reports'
        ordering = ['-generated_at']

    def __str__(self):
        return f"FinalReport for session {self.session.id}"

    @property
    def overall_score(self):
        summary = self.summary or {}

        def score_from(container):
            if not isinstance(container, dict):
                return None
            score_summary = container.get('score_summary')
            if not isinstance(score_summary, dict):
                return None
            return score_summary.get('overall_score')

        raw_data = summary.get('raw_data') if isinstance(summary, dict) else {}
        candidates = (
            score_from(summary),
            score_from(summary.get('summary') if isinstance(summary, dict) else None),
            score_from(raw_data.get('summary') if isinstance(raw_data, dict) else None),
            summary.get('overall_score') if isinstance(summary, dict) else None,
        )
        return next((score for score in candidates if score is not None), None)

    @property
    def is_mock(self):
        summary = self.summary or {}
        metadata = summary.get('evaluation_metadata', {}) if isinstance(summary, dict) else {}
        source = str(metadata.get('source') or summary.get('source') or '').upper()
        return bool(metadata.get('is_mock') or summary.get('is_mock') or source in {'MOCK', 'CAREER_ZIP_MOCK'})

    @property
    def evaluation_status(self):
        if self.is_mock:
            return 'MOCK'
        summary = self.summary or {}
        metadata = summary.get('evaluation_metadata', {}) if isinstance(summary, dict) else {}
        explicit = metadata.get('evaluation_status') or summary.get('evaluation_status')
        if explicit:
            return str(explicit).upper()

        answer_count = int(metadata.get('answer_count') or 0)
        evaluated_count = int(metadata.get('evaluated_answer_count') or 0)
        if answer_count > 0 and evaluated_count == 0:
            return 'FAILED'
        if self.overall_score is None:
            return 'PENDING'
        return 'COMPLETED'

    @property
    def score_status(self):
        if self.is_mock:
            return 'MOCK'
        if self.overall_score is None:
            return 'NOT_EVALUATED'
        return 'SCORED'


class ActionPlan(models.Model):
    STATUS_TODO = 'TODO'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_DONE = 'DONE'

    STATUS_CHOICES = [
        (STATUS_TODO, 'Todo'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_DONE, 'Done'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        FinalReport,
        on_delete=models.CASCADE,
        related_name='action_plans',
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO)
    source_tag = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'report_action_plans'
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['report', 'status'], name='action_report_status_idx'),
        ]

    def __str__(self):
        return f'ActionPlan(report_id={self.report_id}, status={self.status})'
