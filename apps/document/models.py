import uuid

from django.conf import settings
from django.db import models


class UploadedDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('resume', 'Resume'),
        ('cover_letter', 'Cover Letter'),
        ('jd', 'Job Description'),
        ('portfolio', 'Portfolio'),
        ('other', 'Other'),
    ]
    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'DOCX'),
        ('txt', 'TXT'),
    ]
    PARSE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_documents',
    )
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES)
    file_size = models.PositiveIntegerField(default=0)
    parse_status = models.CharField(
        max_length=20,
        choices=PARSE_STATUS_CHOICES,
        default='pending',
    )
    extracted_text = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'uploaded_documents'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_filename} ({self.user})'
