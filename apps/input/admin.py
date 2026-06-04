from django.contrib import admin
from .models import JobDescription


@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'company_name', 'position', 'input_method', 'analysis_status', 'created_at')
    list_filter = ('input_method', 'analysis_status', 'created_at')
    search_fields = ('company_name', 'position', 'original_text')
    readonly_fields = ('created_at', 'updated_at')
