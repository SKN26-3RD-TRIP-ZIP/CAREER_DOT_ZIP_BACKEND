"""E7.7 — A/B 테스트 서비스 레이어.

평가 실행 시 자동으로 variant를 배정하고 결과를 기록한다.
나중에 Firebase Remote Config로 교체 시 이 파일만 수정하면 된다.
"""

import hashlib
import logging

from django.db import transaction
from django.utils import timezone

from apps.evaluation.ab_test_models import (
    ABTestExperiment,
    ABTestAssignment,
    ABTestResult,
)

logger = logging.getLogger("feedback_ai.ab_test")


def _deterministic_variant(user_id: str, experiment_name: str, treatment_ratio: float) -> str:
    """사용자 ID + 실험명의 해시로 variant를 결정적으로 배정한다 (재현 가능).

    동일 사용자는 항상 동일 variant → 쿠키/세션 없이도 일관성 보장.
    """
    seed = f"{user_id}:{experiment_name}"
    hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    bucket = (hash_val % 1000) / 1000.0
    return "treatment" if bucket < treatment_ratio else "control"


def get_or_create_assignment(user_id, experiment_name: str) -> tuple[str, bool]:
    """사용자의 실험 variant를 반환한다 (없으면 새로 배정).

    Args:
        user_id: 사용자 UUID.
        experiment_name: 실험 식별자 (ABTestExperiment.name).

    Returns:
        (variant: str, is_new: bool)
    """
    try:
        experiment = ABTestExperiment.objects.get(name=experiment_name, status="active")
    except ABTestExperiment.DoesNotExist:
        logger.debug("실험 '%s' 미존재 또는 비활성 — control 반환", experiment_name)
        return "control", False

    assignment, created = ABTestAssignment.objects.get_or_create(
        experiment=experiment,
        user_id=user_id,
        defaults={
            "variant": _deterministic_variant(
                str(user_id), experiment_name, experiment.treatment_ratio
            )
        },
    )
    return assignment.variant, created


@transaction.atomic
def record_ab_result(
    experiment_name: str,
    user_id,
    answer_id,
    score_dict: dict,
) -> bool:
    """평가 결과를 A/B 관측값으로 기록한다.

    Args:
        experiment_name: 실험 식별자.
        user_id: 사용자 UUID.
        answer_id: 평가 대상 answer UUID.
        score_dict: {final_score, bei_total, cbi_score, grounding_score,
                     speech_score, sbert_score, emotion_confidence, ...} dict.

    Returns:
        True if recorded, False if experiment not found.
    """
    try:
        experiment = ABTestExperiment.objects.get(name=experiment_name, status="active")
        assignment = ABTestAssignment.objects.get(experiment=experiment, user_id=user_id)
    except (ABTestExperiment.DoesNotExist, ABTestAssignment.DoesNotExist):
        return False

    ABTestResult.objects.create(
        experiment=experiment,
        assignment=assignment,
        answer_id=answer_id,
        final_score=score_dict.get("final_score"),
        bei_total=score_dict.get("bei_total"),
        cbi_score=score_dict.get("cbi_score"),
        grounding_score=score_dict.get("grounding_score"),
        speech_score=score_dict.get("speech_score"),
        sbert_score=score_dict.get("sbert_score"),
        emotion_confidence=score_dict.get("emotion_confidence"),
        extra_metrics={k: v for k, v in score_dict.items() if k not in {
            "final_score", "bei_total", "cbi_score",
            "grounding_score", "speech_score", "sbert_score", "emotion_confidence",
        }},
    )
    return True


# variant 간 비교를 신뢰하기 위한 최소 표본 수 (그룹별)
MIN_SAMPLE_SIZE = 30

_METRICS = [
    "final_score", "bei_total", "cbi_score",
    "grounding_score", "speech_score", "sbert_score", "emotion_confidence",
]


def get_experiment_stats(experiment_name: str) -> dict:
    """실험명으로 집계를 반환한다 (외부 API용)."""
    try:
        experiment = ABTestExperiment.objects.get(name=experiment_name)
    except ABTestExperiment.DoesNotExist:
        return {"error": f"실험 '{experiment_name}'을 찾을 수 없습니다."}
    return stats_for_experiment(experiment)


def stats_for_experiment(experiment) -> dict:
    """실험 인스턴스로 variant 간 점수 비교 집계를 반환한다.

    variant별 집계를 단일 GROUP BY 쿼리로 처리해 N+1을 제거한다.
    표본 수가 MIN_SAMPLE_SIZE 미만이면 delta를 신뢰하지 말라는
    min_sample_met=False 플래그를 함께 반환한다.

    Returns:
        {
            "experiment": str, "status": str,
            "variants": {"control": {...}, "treatment": {...}},
            "delta_treatment_vs_control": {"final_score": float, ...},
            "min_sample_met": bool, "min_sample_size": int,
        }
    """
    from django.db.models import Avg, Count

    agg_fields = {f"avg_{m}": Avg(m) for m in _METRICS}
    agg_fields["count"] = Count("id")

    # 단일 쿼리: variant로 GROUP BY 하여 control/treatment 동시 집계
    grouped = (
        ABTestResult.objects.filter(experiment=experiment)
        .values("assignment__variant")
        .annotate(**agg_fields)
    )

    def _empty():
        return {"count": 0, **{f"avg_{m}": 0 for m in _METRICS}}

    variants_data = {"control": _empty(), "treatment": _empty()}
    for row in grouped:
        variant = row.get("assignment__variant")
        if variant not in variants_data:
            continue
        variants_data[variant] = {
            "count": row.get("count", 0),
            **{f"avg_{m}": round(row.get(f"avg_{m}") or 0, 2) for m in _METRICS},
        }

    ctrl = variants_data["control"]
    trt = variants_data["treatment"]
    delta = {
        m: round((trt[f"avg_{m}"] or 0) - (ctrl[f"avg_{m}"] or 0), 2)
        for m in _METRICS
    }
    min_sample_met = ctrl["count"] >= MIN_SAMPLE_SIZE and trt["count"] >= MIN_SAMPLE_SIZE

    return {
        "experiment": experiment.name,
        "description": experiment.description,
        "target_metric": experiment.target_metric,
        "status": experiment.status,
        "treatment_ratio": experiment.treatment_ratio,
        "created_at": experiment.created_at.isoformat(),
        "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None,
        "variants": variants_data,
        "delta_treatment_vs_control": delta,
        "min_sample_met": min_sample_met,
        "min_sample_size": MIN_SAMPLE_SIZE,
    }
