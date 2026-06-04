import uuid
from django.db import models
from django.conf import settings


class JobDescription(models.Model):
    INPUT_METHOD_CHOICES = [
        ('TEXT', 'Text'),
        ('PDF', 'PDF'),
        ('URL', 'URL'),
        ('OCR', 'OCR'),
    ]

    ANALYSIS_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_descriptions')
    company_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    original_text = models.TextField()
    input_method = models.CharField(max_length=10, choices=INPUT_METHOD_CHOICES, default='TEXT')
    company_summary = models.TextField(blank=True, null=True)
    talent_profile = models.TextField(blank=True, null=True)
    job_requirements = models.TextField(blank=True, null=True)
    keywords = models.TextField(blank=True, null=True)
    analysis_status = models.CharField(max_length=20, choices=ANALYSIS_STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_jobdescription'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} - {self.position}"
