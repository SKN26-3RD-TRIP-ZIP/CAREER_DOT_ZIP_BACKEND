from django.contrib import admin
from .models import FinalReport


@admin.register(FinalReport)
class FinalReportAdmin(admin.ModelAdmin):
  list_display = ('id', 'session', 'overall_score', 'generated_at')
  list_filter = ('generated_at',)
  search_fields = ('session__id',)
  readonly_fields = ('generated_at',)
