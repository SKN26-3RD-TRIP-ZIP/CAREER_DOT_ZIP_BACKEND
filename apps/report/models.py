import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class RoadmapItem(models.Model):
    PRIORITY_CHOICES = [('high', 'high'), ('mid', 'mid'), ('low', 'low')]

    session = models.ForeignKey(
        'interview.InterviewSession',
        on_delete=models.CASCADE,
        related_name='roadmap_items',
    )
    item_id = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'roadmap_items'
        ordering = ['created_at']

    def __str__(self):
        return f"RoadmapItem [{self.item_id}] for session {self.session_id}"


class RoadmapCache(models.Model):
    session = models.OneToOneField(
        'interview.InterviewSession',
        on_delete=models.CASCADE,
        related_name='roadmap_cache',
    )
    week_priority_text = models.TextField()
    practice_question = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'roadmap_cache'

    def __str__(self):
        return f"RoadmapCache for session {self.session_id}"


class FinalReport(models.Model):
    # 비동기 생성 상태. 프론트는 done/failed 가 될 때까지 폴링한다.
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'pending'),
        (STATUS_PROCESSING, 'processing'),
        (STATUS_DONE, 'done'),
        (STATUS_FAILED, 'failed'),
    ]
    # 워커가 처리 중 죽었을 때 'processing' 행을 재시작 가능한 것으로 간주하는 임계 시간(분).
    PROCESSING_TIMEOUT_MINUTES = 10

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        'interview.InterviewSession',
        on_delete=models.CASCADE,
        related_name='final_report',
    )
    summary = models.JSONField(default=dict)
    # 기본값 done: 기존 행(이미 summary 보유)과의 하위호환을 위해.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DONE)
    error_code = models.CharField(max_length=50, blank=True, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feedback_reports'
        ordering = ['-generated_at']

    def __str__(self):
        return f"FinalReport for session {self.session.id}"

    @property
    def is_stale_processing(self):
        """'processing' 상태로 멈춘 지 PROCESSING_TIMEOUT_MINUTES 초과 → 워커 사망으로 간주."""
        if self.status != self.STATUS_PROCESSING:
            return False
        threshold = timezone.now() - timezone.timedelta(minutes=self.PROCESSING_TIMEOUT_MINUTES)
        return self.updated_at < threshold

    @property
    def overall_score(self):
        summary = self.summary or {}

        def score_from(container):
            if not isinstance(container, dict):
                return None
            score_summary = container.get('score_summary')
            if not isinstance(score_summary, dict):
                return None
            return score_summary.get('overall_score')

        raw_data = summary.get('raw_data') if isinstance(summary, dict) else {}
        candidates = (
            score_from(summary),
            score_from(summary.get('summary') if isinstance(summary, dict) else None),
            score_from(raw_data.get('summary') if isinstance(raw_data, dict) else None),
            summary.get('overall_score') if isinstance(summary, dict) else None,
        )
        return next((score for score in candidates if score is not None), None)

    @property
    def is_mock(self):
        summary = self.summary or {}
        metadata = summary.get('evaluation_metadata', {}) if isinstance(summary, dict) else {}
        source = str(metadata.get('source') or summary.get('source') or '').upper()
        return bool(metadata.get('is_mock') or summary.get('is_mock') or source in {'MOCK', 'CAREER_ZIP_MOCK'})

    @property
    def evaluation_status(self):
        if self.is_mock:
            return 'MOCK'
        summary = self.summary or {}
        metadata = summary.get('evaluation_metadata', {}) if isinstance(summary, dict) else {}
        explicit = metadata.get('evaluation_status') or summary.get('evaluation_status')
        if explicit:
            return str(explicit).upper()

        answer_count = int(metadata.get('answer_count') or 0)
        evaluated_count = int(metadata.get('evaluated_answer_count') or 0)
        if answer_count > 0 and evaluated_count == 0:
            return 'FAILED'
        if self.overall_score is None:
            return 'PENDING'
        return 'COMPLETED'

    @property
    def score_status(self):
        if self.is_mock:
            return 'MOCK'
        if self.overall_score is None:
            return 'NOT_EVALUATED'
        return 'SCORED'


class ActionPlan(models.Model):
    STATUS_TODO = 'TODO'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_DONE = 'DONE'

    STATUS_CHOICES = [
        (STATUS_TODO, 'Todo'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_DONE, 'Done'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        FinalReport,
        on_delete=models.CASCADE,
        related_name='action_plans',
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO)
    source_tag = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'report_action_plans'
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['report', 'status'], name='action_report_status_idx'),
        ]

    def __str__(self):
        return f'ActionPlan(report_id={self.report_id}, status={self.status})'

class ReportShareToken(models.Model):
    """단기 유효 리포트 공유 토큰. 만료 후에는 AllowAny 뷰에서 404 처리."""

    EXPIRY_DAYS = 7

    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        FinalReport,
        on_delete=models.CASCADE,
        related_name='share_tokens',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='report_share_tokens',
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'report_share_tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f"ShareToken {self.token} → report {self.report_id} (expires {self.expires_at:%Y-%m-%d})"

    @property
    def is_valid(self):
        return timezone.now() < self.expires_at

    @classmethod
    def get_or_create_for_report(cls, report, user):
        """유효한 토큰이 이미 있으면 재사용, 없으면 신규 발급."""
        existing = (
            cls.objects
            .filter(report=report, created_by=user, expires_at__gt=timezone.now())
            .order_by('-created_at')
            .first()
        )
        if existing:
            return existing, False
        token = cls.objects.create(
            report=report,
            created_by=user,
            expires_at=timezone.now() + timezone.timedelta(days=cls.EXPIRY_DAYS),
        )
        return token, True
