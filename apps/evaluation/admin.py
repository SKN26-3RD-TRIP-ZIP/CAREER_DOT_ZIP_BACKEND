from django.contrib import admin
from .models import Evaluation, WeaknessTag, StrengthTag, AnswerWeaknessTag, AnswerStrengthTag


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ('id', 'answer', 'final_tech_score', 'evaluated_at')
    list_filter = ('evaluated_at', 'final_tech_score')
    search_fields = ('answer__id',)
    readonly_fields = ('evaluated_at', 'updated_at')


@admin.register(WeaknessTag)
class WeaknessTagAdmin(admin.ModelAdmin):
    list_display = ('tag_name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('tag_name', 'description')
    readonly_fields = ('created_at',)


@admin.register(StrengthTag)
class StrengthTagAdmin(admin.ModelAdmin):
    list_display = ('tag_name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('tag_name', 'description')
    readonly_fields = ('created_at',)


@admin.register(AnswerWeaknessTag)
class AnswerWeaknessTagAdmin(admin.ModelAdmin):
    list_display = ('answer', 'weakness_tag', 'priority_rank', 'is_selected_for_followup')
    list_filter = ('is_selected_for_followup', 'priority_rank', 'created_at')
    search_fields = ('answer__id', 'weakness_tag__tag_name')
    readonly_fields = ('created_at',)


@admin.register(AnswerStrengthTag)
class AnswerStrengthTagAdmin(admin.ModelAdmin):
    list_display = ('answer', 'strength_tag', 'priority_rank')
    list_filter = ('priority_rank', 'created_at')
    search_fields = ('answer__id', 'strength_tag__tag_name')
    readonly_fields = ('created_at',)
