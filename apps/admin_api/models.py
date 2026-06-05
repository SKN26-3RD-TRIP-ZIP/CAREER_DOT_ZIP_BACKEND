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
