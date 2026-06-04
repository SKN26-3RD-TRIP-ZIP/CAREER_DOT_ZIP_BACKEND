from django.contrib import admin
from .models import InterviewSession, InterviewQuestion
from .models import InterviewAnswer


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'interview_type', 'persona', 'status', 'total_question_count', 'created_at')
    list_filter = ('interview_type', 'persona', 'status', 'created_at')
    search_fields = ('user__email', 'user__username', 'interview_type', 'persona')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'order_index', 'question_type', 'source_type', 'parent_question', 'source_answer', 'created_at')
    list_filter = ('question_type', 'source_type', 'created_at')
    search_fields = ('question_text', 'source_reference', 'parent_question__question_text', 'source_answer__answer_text')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(InterviewAnswer)
class InterviewAnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'question', 'answer_source', 'created_at')
    list_filter = ('answer_source', 'created_at')
    search_fields = ('answer_text',)
    readonly_fields = ('created_at', 'updated_at')
