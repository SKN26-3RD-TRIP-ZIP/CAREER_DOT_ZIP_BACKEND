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
        return (self.summary or {}).get('score_summary', {}).get('overall_score')
