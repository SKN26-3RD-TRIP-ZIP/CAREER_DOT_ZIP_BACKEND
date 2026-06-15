"""Session-level evaluation orchestration.

이 모듈은 단일 답변 평가 로직(create_evaluation_for_answer)과
세션 단위 일괄 평가(evaluate_session_answers)를 한 곳에서 제공한다.

기존에는 평가(Evaluation) 행과 강점/약점 태그가 오직
EvaluationCreateView(POST /evaluations)에서만 생성되었고,
실제 MVP 면접 플로우(프론트엔드/백엔드 어느 쪽도)에서는 호출되지 않아
최종 리포트가 항상 빈 채로 생성되는 단절이 있었다.

이 서비스를 통해
  - EvaluationCreateView 는 단일 답변 로직을 재사용하고,
  - report 생성 시점(generate_final_report)에 미평가 답변을 자동 백필한다.
모든 동작은 멱등(idempotent)하다: 이미 평가가 있는 답변은 건너뛴다.
"""

import logging

from django.db import transaction
from apps.evaluation.services.sbert_service import (
    compute_sbert_similarities,
    compute_tech_depth_score,
    get_reference_texts_for_answer,
)

from apps.evaluation.models import (
    Evaluation,
    StrengthTag,
    WeaknessTag,
    AnswerStrengthTag,
    AnswerWeaknessTag,
)
from apps.evaluation.services.evaluation_services import EvaluationService
from apps.evaluation.services.sufficiency_bridge import (
    get_answer_text_for_evaluation,
    resolve_answer_sufficiency,
)

logger = logging.getLogger("feedback_ai.session_evaluation")


def _persist_pipeline_tags(answer, pipeline_tags, selected_tag_name):
    """파이프라인이 산출한 강점/약점 태그를 답변에 매핑해 저장한다."""
    for idx, strength in enumerate(pipeline_tags.get("strengths", []), start=1):
        tag_obj, _ = StrengthTag.objects.get_or_create(
            tag_name=strength["tag_name"],
            defaults={"description": strength.get("description", "")},
        )
        AnswerStrengthTag.objects.create(
            answer=answer,
            strength_tag=tag_obj,
            reason=f"[{strength.get('category', 'general')}] {strength.get('description', '')}",
            trigger_signal_log=strength.get("trigger_signal", ""),
            priority_rank=idx,
        )

    for idx, weakness in enumerate(pipeline_tags.get("weaknesses", []), start=1):
        tag_master, _ = WeaknessTag.objects.get_or_create(
            tag_name=weakness["tag_name"],
            defaults={"description": weakness.get("description", "")},
        )
        tag_name = weakness.get("tag_name")
        AnswerWeaknessTag.objects.create(
            answer=answer,
            weakness_tag=tag_master,
            reason=weakness.get("description", ""),
            priority_rank=idx,
            is_selected_for_followup=(
                tag_name == selected_tag_name
                or weakness.get("is_selected_for_followup", False)
            ),
        )


@transaction.atomic
def create_evaluation_for_answer(answer, request_sufficiency=None):
    """단일 InterviewAnswer 에 대한 평가를 생성한다.

    멱등: 이미 Evaluation 이 존재하면 그대로 반환하고 재실행하지 않는다.

    Args:
        answer: 평가 대상 InterviewAnswer 인스턴스.
        request_sufficiency: 면접(turns) 플로우가 전달한 충분성 페이로드(dict) 또는 None.

    Returns:
        생성되었거나 기존에 존재하던 Evaluation 인스턴스.
    """
    existing = Evaluation.objects.filter(answer=answer).first()
    if existing is not None:
        return existing

    answer_text = get_answer_text_for_evaluation(answer)
    question_type = answer.session.interview_type or "technical"

    llm_weakness_tags, selected_weakness_tag = resolve_answer_sufficiency(
        answer,
        request_sufficiency=request_sufficiency,
    )
    selected_tag_name = (
        selected_weakness_tag.get("tag_name")
        if isinstance(selected_weakness_tag, dict)
        else None
    )

    ai_result = EvaluationService.run_pipeline(
        answer_text=answer_text,
        question_type=question_type,
        long_pause_count=answer.long_pause_count or 0,
        llm_weakness_tags=llm_weakness_tags,
    )

    pipeline_tags = ai_result.pop("pipeline_tags", {"strengths": [], "weaknesses": []})
    emotion_intent_score = ai_result.pop("emotion_intent_score", {})
    pause_analysis = ai_result.get("score_detail", {}).get("pause_analysis", {})

    # E7.5 — SBERT 하드스킬 깊이 검증 (기술 질문일 때만 실행)
    sbert_db_similarity = None
    sbert_readme_similarity = None
    if question_type == "technical":
        try:
            ref_db, ref_readme = get_reference_texts_for_answer(answer)
            sbert_res = compute_sbert_similarities(
                answer_text=answer_text,
                reference_db_text=ref_db,
                reference_readme_text=ref_readme,
            )
            sbert_db_similarity = sbert_res["sbert_db_similarity"]
            sbert_readme_similarity = sbert_res["sbert_readme_similarity"]

            if sbert_res["model_available"] and sbert_res["sbert_combined_score"] > 0:
                llm_concept = ai_result.get("final_tech_score") or 0
                hybrid_score = compute_tech_depth_score(
                    sbert_combined_score=sbert_res["sbert_combined_score"],
                    llm_concept_score=llm_concept,
                )
                ai_result["final_tech_score"] = int(hybrid_score)
                logger.info(
                    "SBERT 하이브리드 스코어 적용: sbert=%.1f, llm=%d → final=%d",
                    sbert_res["sbert_combined_score"], llm_concept, int(hybrid_score),
                )
        except Exception:
            logger.exception("SBERT 평가 실패 — final_tech_score 기존 값 유지")

    evaluation = Evaluation.objects.create(
        answer=answer,
        bei_score=ai_result["bei_score"],
        cbi_score=ai_result["cbi_score"],
        filler_words=ai_result["filler_words"],
        final_tech_score=ai_result["final_tech_score"],
        score_detail=ai_result["score_detail"],
        emotion_intent_score=emotion_intent_score,      # E7.4
        pause_analysis=pause_analysis,                  # E7.6
        sbert_db_similarity=sbert_db_similarity,        # E7.5
        sbert_readme_similarity=sbert_readme_similarity, # E7.5
    )

    _persist_pipeline_tags(answer, pipeline_tags, selected_tag_name)

    return evaluation


def evaluate_session_answers(session, reevaluate=False):
    """세션의 모든 답변을 평가한다(미평가분 백필).

    멱등하며 답변별로 예외를 격리한다: 한 답변 평가가 실패해도
    나머지 답변과 리포트 생성은 계속 진행된다.

    Args:
        session: InterviewSession 인스턴스.
        reevaluate: True 이면 기존 평가/태그를 삭제하고 다시 평가한다.

    Returns:
        {'evaluated': int, 'skipped': int, 'failed': int} 집계 딕셔너리.
    """
    stats = {"evaluated": 0, "skipped": 0, "failed": 0}

    answers = session.answers.select_related("session").all()
    for answer in answers:
        # 답변 본문이 비어 있으면 평가 의미가 없으므로 건너뜀.
        if not (answer.answer_text or answer.stt_text):
            stats["skipped"] += 1
            continue

        already_evaluated = Evaluation.objects.filter(answer=answer).exists()
        if already_evaluated and not reevaluate:
            stats["skipped"] += 1
            continue

        try:
            if already_evaluated and reevaluate:
                with transaction.atomic():
                    answer.strength_mappings.all().delete()
                    answer.weakness_mappings.all().delete()
                    Evaluation.objects.filter(answer=answer).delete()

            create_evaluation_for_answer(answer)
            stats["evaluated"] += 1
        except Exception:  # noqa: BLE001 - 답변 단위 격리, 리포트는 계속 생성
            logger.exception(
                "Session evaluation backfill failed for answer %s (session %s)",
                getattr(answer, "id", "?"),
                getattr(session, "id", "?"),
            )
            stats["failed"] += 1

    if stats["evaluated"] or stats["failed"]:
        logger.info(
            "evaluate_session_answers(session=%s) -> %s",
            getattr(session, "id", "?"),
            stats,
        )
    return stats
