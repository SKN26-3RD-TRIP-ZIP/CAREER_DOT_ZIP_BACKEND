from django.contrib import admin
from .models import JobDescription, UserProfile


@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'company_name', 'position', 'input_method', 'analysis_status', 'created_at')
    list_filter = ('input_method', 'analysis_status', 'created_at')
    search_fields = ('company_name', 'position', 'original_text')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'career_type', 'major_type', 'desired_job', 'career_year', 'created_at', 'updated_at')
    list_filter = ('career_type', 'major_type', 'career_year', 'created_at')
    search_fields = ('user__email', 'desired_job')
    readonly_fields = ('created_at', 'updated_at')
