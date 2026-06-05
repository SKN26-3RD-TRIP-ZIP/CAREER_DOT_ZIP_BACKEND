import uuid

from django.db import models


class QuestionBankItem(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('technical', 'Technical'),
        ('personality', 'Personality'),
        ('job', 'Job'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_category = models.CharField(max_length=100, default='ICT', db_index=True)
    question_text = models.TextField()
    answer_example = models.TextField(blank=True)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    keywords = models.JSONField(default=list)
    source = models.CharField(max_length=50, default='aihub', db_index=True)
    source_file = models.CharField(max_length=255, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    raw_metadata = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'question_bank_items'
        ordering = ['-created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=('source', 'source_file', 'question_text'),
                name='unique_question_bank_source_file_text',
            )
        ]
        indexes = [
            models.Index(
                fields=('job_category', 'question_type', 'difficulty'),
                name='qbank_job_type_diff_idx',
            ),
            models.Index(
                fields=('source', 'source_file'),
                name='qbank_source_file_idx',
            ),
        ]

    def __str__(self):
        return self.question_text[:80]
