from django.conf import settings
from django.db import models


class PointHistory(models.Model):
    REASON_CHOICES = [
        # 적립
        ('ATTENDANCE', '출석 적립'),
        ('INTERVIEW_COMPLETE', '면접 완료 적립'),
        ('REPORT_COMPLETE', '리포트 완료 적립'),
        ('EVENT', '이벤트 적립'),
        ('ADMIN_GRANT', '관리자 지급'),
        # 사용
        ('INTERVIEW_USE', '면접 사용'),
        ('REPORT_USE', '리포트 사용'),
        # 환불
        ('REFUND', '환불'),
        # 만료
        ('EXPIRE', '만료'),
        # 조정
        ('ADMIN_ADJUST', '관리자 조정'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='point_histories',
        db_index=True,
    )
    amount = models.IntegerField()  # 적립: 양수, 사용/만료: 음수
    reason_code = models.CharField(max_length=30, choices=REASON_CHOICES)
    reference_id = models.BigIntegerField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    balance_after = models.IntegerField()
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'point_history'
        verbose_name = 'Point History'
        verbose_name_plural = 'Point Histories'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='ph_user_created_idx'),
            models.Index(fields=['expires_at'], name='ph_expires_idx'),
        ]

    def __str__(self):
        return f'PointHistory(user_id={self.user_id}, amount={self.amount}, reason={self.reason_code})'
