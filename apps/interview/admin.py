from django.contrib import admin
from .models import InterviewSession, InterviewQuestion


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'interview_type', 'persona', 'status', 'total_question_count', 'created_at')
    list_filter = ('interview_type', 'persona', 'status', 'created_at')
    search_fields = ('user__email', 'user__username', 'interview_type', 'persona')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'order_index', 'question_type', 'source_type', 'created_at')
    list_filter = ('question_type', 'source_type', 'created_at')
    search_fields = ('question_text', 'source_reference')
    readonly_fields = ('created_at', 'updated_at')
