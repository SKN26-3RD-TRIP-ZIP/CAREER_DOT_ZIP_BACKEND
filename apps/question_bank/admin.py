from django.contrib import admin

from .models import QuestionBankItem


@admin.register(QuestionBankItem)
class QuestionBankItemAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'job_category',
        'question_type',
        'difficulty',
        'source',
        'source_file',
        'is_active',
        'created_at',
    )
    list_filter = ('job_category', 'question_type', 'difficulty', 'source', 'is_active')
    search_fields = ('question_text', 'answer_example', 'source_file', 'source_ref')
    readonly_fields = ('created_at', 'updated_at')
