from django.contrib import admin
from .models import (
    JobDescription,
    TalentProfileCategory,
    TalentProfileTrait,
    JDTalentProfile,
    JDTalentProfileItem,
    ProjectExperience,
    CoverLetter,
    CoverLetterItem,
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


@admin.register(TalentProfileCategory)
class TalentProfileCategoryAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'category_code', 'category_name', 'display_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('category_code', 'category_name', 'short_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TalentProfileTrait)
class TalentProfileTraitAdmin(admin.ModelAdmin):
    list_display = ('trait_id', 'trait_code', 'trait_name', 'category', 'display_order', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('trait_code', 'trait_name', 'short_description')
    readonly_fields = ('created_at', 'updated_at')


class JDTalentProfileItemInline(admin.TabularInline):
    model = JDTalentProfileItem
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


@admin.register(JDTalentProfile)
class JDTalentProfileAdmin(admin.ModelAdmin):
    list_display = ('jd_talent_profile_id', 'jd', 'source_type', 'confirmed_by_user', 'confirmed_at', 'updated_at')
    list_filter = ('source_type', 'confirmed_by_user')
    search_fields = ('jd__company_name', 'jd__position', 'custom_summary', 'source_text')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [JDTalentProfileItemInline]


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


@admin.register(CoverLetter)
class CoverLetterAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'company_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'company_name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CoverLetterItem)
class CoverLetterItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cover_letter', 'order_index', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('cover_letter__title', 'question', 'answer_text')
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
