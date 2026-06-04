import uuid
from django.db import models
from django.conf import settings


class FinalReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='final_reports')
    session = models.OneToOneField('interview.InterviewSession', on_delete=models.CASCADE, related_name='final_report')
    overall_score = models.PositiveIntegerField(default=0)
    summary = models.TextField(blank=True)
    strengths = models.JSONField(default=list)
    weaknesses = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    question_count = models.PositiveIntegerField(default=0)
    answer_count = models.PositiveIntegerField(default=0)
    evaluated_answer_count = models.PositiveIntegerField(default=0)
    raw_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'final_reports'
        ordering = ['-created_at']

    def __str__(self):
        return f"FinalReport for session {self.session.id}"