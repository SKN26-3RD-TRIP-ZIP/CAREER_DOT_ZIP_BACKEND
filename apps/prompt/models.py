from django.conf import settings
from django.db import models

from apps.common.choices import INTERVIEW_PERSONA_CHOICES


class PersonaConfig(models.Model):
    persona_type = models.CharField(
        max_length=30,
        choices=INTERVIEW_PERSONA_CHOICES,
        unique=True,
    )
    description = models.TextField(blank=True)
    active_template = models.ForeignKey(
        'PromptTemplate',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_personas',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'persona_configs'
        ordering = ['persona_type']

    def __str__(self):
        return self.persona_type


class PromptTemplate(models.Model):
    PROMPT_TYPE_CHOICES = [
        ('question_generation', 'Question Generation'),
        ('answer_evaluation', 'Answer Evaluation'),
        ('follow_up_generation', 'Follow-up Generation'),
        ('final_report', 'Final Report'),
    ]

    persona_config = models.ForeignKey(
        PersonaConfig,
        on_delete=models.CASCADE,
        related_name='prompt_templates',
    )
    title = models.CharField(max_length=100)
    prompt_type = models.CharField(max_length=50, choices=PROMPT_TYPE_CHOICES)
    default_version = models.ForeignKey(
        'PromptVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='default_templates',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prompt_templates'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class PromptVersion(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'
    STATUS_ROLLED_BACK = 'ROLLED_BACK'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_ROLLED_BACK, 'Rolled Back'),
    ]

    template = models.ForeignKey(
        PromptTemplate,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    content = models.TextField()
    change_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    interview_type = models.CharField(max_length=30, blank=True, default='')
    feature_key = models.CharField(max_length=50, blank=True, default='')
    model_name = models.CharField(max_length=80, blank=True, default='')
    activated_at = models.DateTimeField(null=True, blank=True, default=None)
    deactivated_at = models.DateTimeField(null=True, blank=True, default=None)
    rollback_from = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rollback_versions',
    )
    test_result = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'prompt_versions'
        ordering = ['-version_number']
        constraints = [
            models.UniqueConstraint(
                fields=('template', 'version_number'),
                name='unique_prompt_template_version',
            )
        ]

    def __str__(self):
        return f'{self.template.title} v{self.version_number}'


class AdminPromptTestRun(models.Model):
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_prompt_test_runs',
    )
    prompt_version = models.ForeignKey(
        PromptVersion,
        on_delete=models.CASCADE,
        related_name='admin_test_runs',
    )
    session = models.OneToOneField(
        'interview.InterviewSession',
        on_delete=models.CASCADE,
        related_name='admin_prompt_test_run',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_prompt_test_runs'
        ordering = ['-created_at']

    def __str__(self):
        return f'admin-test session={self.session_id} prompt_version={self.prompt_version_id}'
