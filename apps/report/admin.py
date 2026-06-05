from django.contrib import admin
from .models import FinalReport


@admin.register(FinalReport)
class FinalReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session', 'overall_score', 'question_count', 'answer_count', 'evaluated_answer_count', 'created_at')
    list_filter = ('overall_score', 'created_at')
    search_fields = ('user__email', 'user__username', 'session__id')
    readonly_fields = ('created_at', 'updated_at')
