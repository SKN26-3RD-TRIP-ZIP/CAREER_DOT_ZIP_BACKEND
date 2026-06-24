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
