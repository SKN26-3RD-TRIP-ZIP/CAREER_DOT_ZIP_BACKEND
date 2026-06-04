from django.contrib import admin
from .models import (
    JobDescription,
    ProjectExperience,
    ResumeMaster,
    UserProfile,
    ResumeEducation,
    ResumeCareer,
    ResumeSkill,
    ResumeCertificate,
)


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


@admin.register(ResumeMaster)
class ResumeMasterAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'email', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'name', 'email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectExperience)
class ProjectExperienceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'project_name', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('project_name', 'description', 'contribution', 'github_url', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ResumeEducation)
class ResumeEducationAdmin(admin.ModelAdmin):
    list_display = ('id', 'resume', 'school_name', 'degree', 'status', 'created_at')
    list_filter = ('degree', 'status', 'created_at')
    search_fields = ('resume__user__email', 'school_name', 'major')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ResumeCareer)
class ResumeCareerAdmin(admin.ModelAdmin):
    list_display = ('id', 'resume', 'company_name', 'position', 'is_current', 'created_at')
    list_filter = ('is_current', 'created_at')
    search_fields = ('resume__user__email', 'company_name', 'position')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ResumeSkill)
class ResumeSkillAdmin(admin.ModelAdmin):
    list_display = ('id', 'resume', 'name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('resume__user__email', 'name')
    readonly_fields = ('created_at',)


@admin.register(ResumeCertificate)
class ResumeCertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'resume', 'name', 'issued_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('resume__user__email', 'name', 'issued_by')
    readonly_fields = ('created_at', 'updated_at')
