from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'actor',
        'action_type',
        'target_type',
        'target_id',
        'created_at',
    )
    list_filter = ('action_type', 'target_type', 'created_at')
    search_fields = ('actor__email', 'action_type', 'target_type', 'target_id')
    readonly_fields = (
        'actor',
        'action_type',
        'target_type',
        'target_id',
        'before_value',
        'after_value',
        'created_at',
    )
