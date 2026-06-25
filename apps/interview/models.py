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


class InterviewAnswer(models.Model):
    ANSWER_SOURCE_CHOICES = ANSWER_SOURCE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='answers')
    question = models.OneToOneField('InterviewQuestion', on_delete=models.CASCADE, related_name='answer')
    answer_text = models.TextField()
    answer_source = models.CharField(max_length=20, choices=ANSWER_SOURCE_CHOICES, default='text')
    stt_text = models.TextField(blank=True, null=True)
    audio_url = models.URLField(blank=True, null=True)
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
