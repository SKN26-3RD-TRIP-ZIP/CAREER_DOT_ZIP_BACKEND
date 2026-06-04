import uuid
from django.db import models
from django.conf import settings


class InterviewSession(models.Model):
    INTERVIEW_TYPE_CHOICES = [
        ('technical', 'Technical'),
        ('personality', 'Personality'),
        ('comprehensive', 'Comprehensive'),
    ]
    PERSONA_CHOICES = [
        ('coach', 'Coach'),
        ('practical', 'Practical'),
        ('verifier', 'Verifier'),
        ('pressure', 'Pressure'),
    ]
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='interview_sessions')
    jd = models.ForeignKey('input.JobDescription', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    resume = models.ForeignKey('input.ResumeMaster', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    cover_letter = models.ForeignKey('input.CoverLetter', on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_sessions')
    interview_type = models.CharField(max_length=20, choices=INTERVIEW_TYPE_CHOICES)
    persona = models.CharField(max_length=20, choices=PERSONA_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
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
    QUESTION_TYPE_CHOICES = [
        ('main', 'Main'),
        ('follow_up', 'Follow Up'),
    ]

    SOURCE_TYPE_CHOICES = [
        ('jd', 'JD'),
        ('resume', 'Resume'),
        ('cover_letter', 'Cover Letter'),
        ('project', 'Project'),
        ('profile', 'Profile'),
        ('general', 'General'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions')
    order_index = models.PositiveIntegerField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='main')
    question_text = models.TextField()
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='general')
    source_reference = models.CharField(max_length=100, blank=True, null=True)
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
