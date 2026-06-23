from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='admin_audit_logs',
    )
    action_type = models.CharField(max_length=50)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    before_value = models.JSONField(default=dict, blank=True)
    after_value = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action_type}: {self.target_type} {self.target_id}'


class LlmUsageLog(models.Model):
    model = models.CharField(max_length=64)
    prompt_tokens = models.IntegerField()
    completion_tokens = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        db_table = 'llm_usage_log'


class ApiErrorLog(models.Model):
    """API 5xx 응답(미처리 예외 포함) 기록. 대시보드 24h 에러 수 집계용.

    에러는 드물게 발생하므로 적재 비용이 낮다. ResponseTimeMiddleware에서 기록한다.
    """
    path = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'api_error_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.status_code} {self.method} {self.path}'
