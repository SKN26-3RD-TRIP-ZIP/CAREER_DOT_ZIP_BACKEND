"""E7.7 — 평가 기법 A/B 테스트 모델.

Django DB 기반으로 실험군/대조군 배정, 평가 결과 기록,
집계 분석을 제공한다. Firebase Remote Config 없이도 동작하며
나중에 Firebase로 교체 가능한 인터페이스를 유지한다.
"""

import uuid
from django.db import models


class ABTestExperiment(models.Model):
    """A/B 실험 정의 테이블."""

    STATUS_CHOICES = [
        ("active", "진행 중"),
        ("paused", "일시 중단"),
        ("completed", "종료"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, help_text="실험 식별자 (예: eval_method_v2)")
    description = models.TextField(blank=True)
    # 실험 대상 평가 기법: "grounding_v1", "sbert_hybrid", "emotion_intent" 등
    target_metric = models.CharField(max_length=100)
    # 실험군 비율 (0.0~1.0), 나머지는 대조군
    treatment_ratio = models.FloatField(default=0.5)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ab_test_experiments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.name}"


class ABTestAssignment(models.Model):
    """사용자 × 실험 배정 기록. 동일 사용자는 항상 같은 variant를 받는다."""

    VARIANT_CHOICES = [
        ("control", "대조군"),
        ("treatment", "실험군"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    experiment = models.ForeignKey(
        ABTestExperiment,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    user_id = models.BigIntegerField(db_index=True)  # User.id is BigAutoField(int)
    variant = models.CharField(max_length=20, choices=VARIANT_CHOICES)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ab_test_assignments"
        unique_together = [("experiment", "user_id")]
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.experiment.name} / user={self.user_id} / {self.variant}"


class ABTestResult(models.Model):
    """평가 1건에 대한 A/B 관측값 기록."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    experiment = models.ForeignKey(
        ABTestExperiment,
        on_delete=models.CASCADE,
        related_name="results",
    )
    assignment = models.ForeignKey(
        ABTestAssignment,
        on_delete=models.CASCADE,
        related_name="results",
    )
    # 평가 대상 answer ID (evaluation FK 대신 UUID만 보관 — 순환 의존 방지)
    answer_id = models.UUIDField(db_index=True)
    # 관측 지표들
    final_score = models.FloatField(null=True, blank=True)
    bei_total = models.FloatField(null=True, blank=True)
    cbi_score = models.FloatField(null=True, blank=True)
    grounding_score = models.FloatField(null=True, blank=True)
    speech_score = models.FloatField(null=True, blank=True)
    sbert_score = models.FloatField(null=True, blank=True)
    emotion_confidence = models.FloatField(null=True, blank=True)
    # 자유 형식 추가 메타데이터
    extra_metrics = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ab_test_results"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.experiment.name} / {self.assignment.variant} / answer={self.answer_id}"
