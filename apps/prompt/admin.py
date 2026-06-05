from django.contrib import admin

from .models import PersonaConfig, PromptTemplate, PromptVersion


@admin.register(PersonaConfig)
class PersonaConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'persona_type', 'active_template', 'is_active', 'updated_at')
    list_filter = ('persona_type', 'is_active')
    search_fields = ('persona_type', 'description')


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'persona_config',
        'prompt_type',
        'default_version',
        'is_active',
        'updated_at',
    )
    list_filter = ('prompt_type', 'is_active', 'persona_config__persona_type')
    search_fields = ('title',)


@admin.register(PromptVersion)
class PromptVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'template', 'version_number', 'created_by', 'created_at')
    list_filter = ('template__prompt_type', 'created_at')
    search_fields = ('template__title', 'content', 'change_note')
