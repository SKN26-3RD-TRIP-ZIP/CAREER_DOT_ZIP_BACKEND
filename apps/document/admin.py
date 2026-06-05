from django.contrib import admin

from .models import UploadedDocument


@admin.register(UploadedDocument)
class UploadedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'document_type',
        'original_filename',
        'file_type',
        'file_size',
        'parse_status',
        'created_at',
    )
    list_filter = ('document_type', 'file_type', 'parse_status', 'created_at')
    search_fields = ('original_filename', 'user__email', 'extracted_text')
    readonly_fields = ('file_size', 'parse_status', 'created_at', 'updated_at')
