from django.contrib import admin
from .models import AnalysisSession, GeneratedQuestion


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    list_display    = ["id", "user", "job_role", "company_name", "status", "created_at"]
    list_filter     = ["status", "job_role"]
    search_fields   = ["user__username", "company_name"]
    readonly_fields = ["jd_keywords", "resume_analysis", "created_at", "updated_at"]


@admin.register(GeneratedQuestion)
class GeneratedQuestionAdmin(admin.ModelAdmin):
    list_display  = ["id", "session", "question_type", "question_text", "order", "is_used"]
    list_filter   = ["question_type", "is_used"]
    search_fields = ["question_text"]
