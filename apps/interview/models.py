import uuid
from django.db import models
from django.conf import settings

from apps.common.choices import (
    ANSWER_SOURCE_CHOICES,
    INTERVIEW_PERSONA_CHOICES,
    INTERVIEW_SESSION_STATUS_CHOICES,
    INTERVIEW_TYPE_CHOICES,
    QUESTION_CATEGORY_CHOICES,
    QUESTION_TYPE_CHOICES,
)

# interview_type controls the question content mix (technical, personality,
# comprehensive). interview_mode controls the interaction channel (text,
# voice). These fields serve different purposes and must remain separate.


class InterviewSession(models.Model):
    INTERVIEW_TYPE_CHOICES = INTERVIEW_TYPE_CHOICES
    PERSONA_CHOICES = INTERVIEW_PERSONA_CHOICES
    STATUS_CHOICES = INTERVIEW_SESSION_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='interview_sessions')
    jd = models.ForeignKey('input.JobDescription', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    resume = models.ForeignKey('input.ResumeMaster', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    cover_letter = models.ForeignKey('input.CoverLetter', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    interview_type = models.CharField(max_length=20, choices=INTERVIEW_TYPE_CHOICES)
    persona = models.CharField(max_length=20, choices=INTERVIEW_PERSONA_CHOICES)
    status = models.CharField(max_length=20, choices=INTERVIEW_SESSION_STATUS_CHOICES, default='created')
    interview_mode = models.CharField(
        max_length=10,
        choices=[('text', 'Text'), ('voice', 'Voice')],
        default='text',
    )
    total_question_count = models.PositiveIntegerField(default=3)
    current_question_index = models.PositiveIntegerField(default=0)
    prompt_version_snapshot = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'interview_sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"InterviewSession {self.id} ({self.user})"


class InterviewQuestion(models.Model):
    QUESTION_TYPE_CHOICES = QUESTION_TYPE_CHOICES

    SOURCE_TYPE_CHOICES = [
        ('jd', 'JD'),
        ('resume', 'Resume'),
        ('cover_letter', 'Cover Letter'),
        ('project', 'Project'),
        ('project_experience', 'Project Experience'),
        ('combined', 'Combined'),
        ('prepared_question', 'Prepared Question'),
        ('question_bank', 'Question Bank'),
        ('profile', 'Profile'),
        ('rule', 'Rule'),
        ('general', 'General'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions')
    order_index = models.PositiveIntegerField()
    # Structural role used by turn and follow-up flow: main or follow_up.
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='main')
    # Content classification: technical, personality, or general.
    question_category = models.CharField(max_length=20, choices=QUESTION_CATEGORY_CHOICES, default='general')
    question_text = models.TextField()
    difficulty = models.CharField(max_length=20, blank=True, null=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='general')
    source_reference = models.CharField(max_length=100, blank=True, null=True)
    parent_question = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='follow_up_questions')
    source_answer = models.ForeignKey('InterviewAnswer', on_delete=models.CASCADE, null=True, blank=True, related_name='follow_up_questions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'interview_questions'
        ordering = ['order_index']
        constraints = [
            models.UniqueConstraint(fields=['session', 'order_index'], name='unique_session_order_index')
        ]

    def __str__(self):
        return f"Q{self.order_index} for session {self.session.id}"


class QuestionSourceTag(models.Model):
    SOURCE_TYPE_CHOICES = InterviewQuestion.SOURCE_TYPE_CHOICES

    id = models.BigAutoField(primary_key=True)
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.CASCADE,
        related_name='source_tags',
    )
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES, default='general')
    source_label = models.CharField(max_length=100, blank=True, default='')
    source_text_excerpt = models.TextField(blank=True, default='')
    source_reference = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'question_source_tags'
        ordering = ['id']

    def __str__(self):
        return f'{self.source_type} for question {self.question_id}'


class QuestionPack(models.Model):
    STATUS_READY = 'READY'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='question_packs')
    title = models.CharField(max_length=150)
    interview_type = models.CharField(max_length=20, choices=INTERVIEW_TYPE_CHOICES, default='technical')
    mix = models.JSONField(default=dict, blank=True)
    questions = models.JSONField(default=list, blank=True)
    prompt_version_snapshot = models.JSONField(default=dict, blank=True)
    generation_model = models.CharField(max_length=80, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_READY)
    is_fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'interview_question_packs'
        ordering = ['-created_at']

    def __str__(self):
        return f'QuestionPack {self.id} ({self.user_id})'


class InterviewAnswer(models.Model):
    ANSWER_SOURCE_CHOICES = ANSWER_SOURCE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='answers')
    question = models.OneToOneField('InterviewQuestion', on_delete=models.CASCADE, related_name='answer')
    answer_text = models.TextField()
    answer_source = models.CharField(max_length=20, choices=ANSWER_SOURCE_CHOICES, default='text')
    stt_text = models.TextField(blank=True, null=True)
    audio_url = models.URLField(blank=True, null=True)
    audio_key = models.CharField(max_length=512, blank=True, null=True)
    speech_duration = models.FloatField(blank=True, null=True)
    total_pause_duration = models.FloatField(default=0)
    long_pause_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'interview_answers'
        ordering = ['question__order_index']

    def __str__(self):
        return f"Answer for Q{self.question.order_index} (session {self.session.id})"


class GuardrailEvent(models.Model):
    CATEGORY_CHOICES = [
        ('G0', 'Normal'),
        ('G1', 'Low Quality'),
        ('G2', 'Repeated Or Irrelevant'),
        ('G3', 'Sensitive Or Injection'),
        ('G4', 'Harmful Or Illegal'),
        ('G5', 'Automation Or Privilege Abuse'),
    ]
    ACTION_CHOICES = [
        ('ALLOW', 'Allow'),
        ('GUIDE', 'Guide'),
        ('WARN', 'Warn'),
        ('BLOCK_INPUT', 'Block Input'),
        ('SKIP_FOLLOWUP', 'Skip Follow-up'),
        ('END_SESSION', 'End Session'),
        ('REQUIRE_ADMIN_REVIEW', 'Require Admin Review'),
    ]
    STAGE_CHOICES = [
        ('SIGNUP', 'Signup'),
        ('MYPAGE', 'Mypage'),
        ('INTERVIEW', 'Interview'),
        ('REPORT', 'Report'),
    ]
    DIRECTION_CHOICES = [
        ('USER_TO_AI', 'User To AI'),
        ('AI_TO_USER', 'AI To User'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='guardrail_events')
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='guardrail_events', null=True, blank=True)
    question = models.ForeignKey(InterviewQuestion, on_delete=models.SET_NULL, related_name='guardrail_events', null=True, blank=True)
    answer = models.ForeignKey(InterviewAnswer, on_delete=models.SET_NULL, related_name='guardrail_events', null=True, blank=True)
    category = models.CharField(max_length=2, choices=CATEGORY_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='INTERVIEW')
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default='USER_TO_AI')
    rule_source = models.CharField(max_length=20, default='RULE')
    reason_code = models.CharField(max_length=80)
    masked_excerpt = models.CharField(max_length=240, blank=True, default='')
    endpoint = models.CharField(max_length=120, blank=True, default='')
    retention_until = models.DateTimeField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'guardrail_events'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['category', 'created_at'], name='guardrail_cat_created_idx'),
            models.Index(fields=['user', 'created_at'], name='guardrail_user_created_idx'),
            models.Index(fields=['stage', 'direction', 'created_at'], name='guardrail_stage_dir_idx'),
        ]

    def __str__(self):
        return f'GuardrailEvent(user_id={self.user_id}, category={self.category}, action={self.action})'
