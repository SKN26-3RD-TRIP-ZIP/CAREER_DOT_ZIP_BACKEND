from django.contrib import admin
from .models import InterviewSession


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'interview_type', 'persona', 'status', 'total_question_count', 'created_at')
    list_filter = ('interview_type', 'persona', 'status', 'created_at')
    search_fields = ('user__email', 'user__username', 'interview_type', 'persona')
    readonly_fields = ('created_at', 'updated_at')
