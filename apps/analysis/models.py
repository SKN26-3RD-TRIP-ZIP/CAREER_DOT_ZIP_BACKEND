from django.db import models
from django.contrib.auth import get_user_model
from common.constants import 

User = get_user_model()


class AnalysisSession(models.Model):
    """
    사용자 입력 → 분석 → 질문 생성까지를 묶는 단위.
    면접 진행(interview 앱)은 이 session_id를 FK로 참조한다.
    """
    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name="analysis_sessions")
    job_role          = models.CharField(max_length=100)
    company_name      = models.CharField(max_length=100, blank=True)
    jd_text           = models.TextField()
    resume_text       = models.TextField(blank=True)
    cover_letter_text = models.TextField(blank=True)

    # 분석 결과
    jd_keywords     = models.JSONField(default=list)
    resume_analysis = models.JSONField(default=dict)

    STATUS_CHOICES = [
        ("pending",   "분석 대기"),
        ("analyzing", "분석 중"),
        ("ready",     "완료"),
        ("failed",    "실패"),
    ]
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.user}] {self.job_role} @ {self.company_name} ({self.status})"


class GeneratedQuestion(models.Model):
    """
    AnalysisSession에 연결된 사전 생성 예상 질문.
    interview 앱에서 session_id로 이 테이블을 조회한다.
    """
    session = models.ForeignKey(
        AnalysisSession, on_delete=models.CASCADE, related_name="questions"
    )

    QUESTION_TYPES = [
        ("personality", "인성"),
        ("technical",   "기술·직무"),
        ("experience",  "경험 기반"),
    ]
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    question_text = models.TextField()
    order         = models.IntegerField(default=0)
    is_used       = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"[{self.question_type}] {self.question_text[:40]}"
