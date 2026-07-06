from django.contrib import admin
from .models import (
    AnalysisSession, JdAnalysis, GeneratedQuestion, ConglomerateCompany, IndustryTalentProfile,
)


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    list_display    = ["id", "user", "job_role", "company_name", "status", "created_at"]
    list_filter     = ["status", "job_role"]
    search_fields   = ["user__email", "company_name"]
    readonly_fields = ["jd_keywords", "resume_analysis", "created_at", "updated_at"]


@admin.register(JdAnalysis)
class JdAnalysisAdmin(admin.ModelAdmin):
    list_display    = ["id", "user", "jd", "resume", "match_score", "analyzed_at"]
    list_filter     = ["match_score"]
    search_fields   = ["user__email"]
    readonly_fields = ["jd_keywords", "resume_analysis", "strengths", "weaknesses", "cl_points"]


@admin.register(GeneratedQuestion)
class GeneratedQuestionAdmin(admin.ModelAdmin):
    list_display  = ["id", "jd_analysis", "question_type", "question_text", "order", "is_used"]
    list_filter   = ["question_type", "is_used"]
    search_fields = ["question_text"]


@admin.register(ConglomerateCompany)
class ConglomerateCompanyAdmin(admin.ModelAdmin):
    list_display  = ["group_name", "company_name"]
    list_filter   = ["group_name"]
    search_fields = ["company_name", "group_name"]


@admin.register(IndustryTalentProfile)
class IndustryTalentProfileAdmin(admin.ModelAdmin):
    list_display  = ["industry", "talent_keywords", "created_at"]
    search_fields = ["industry"]
