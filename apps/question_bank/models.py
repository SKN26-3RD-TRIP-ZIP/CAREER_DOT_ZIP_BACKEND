import hashlib
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
    # MySQL은 TEXT 컬럼에 unique 인덱스 불가 → question_text의 SHA-256 해시로 중복 체크
    question_hash = models.CharField(max_length=64, blank=True, db_index=True)
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
            # question_text 대신 question_hash로 유니크 제약
            models.UniqueConstraint(
                fields=('source', 'source_file', 'question_hash'),
                name='unique_question_bank_source_file_hash',
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

    def save(self, *args, **kwargs):
        # question_text 저장 시 해시 자동 생성
        self.question_hash = hashlib.sha256(self.question_text.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.question_text[:80]
