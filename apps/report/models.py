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
