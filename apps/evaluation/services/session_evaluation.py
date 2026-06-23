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

from django.conf import settings
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
from apps.evaluation.evaluation_chains import EvaluationFormatError
from apps.evaluation.services.evaluation_services import EvaluationService
from apps.evaluation.services.question_category import resolve_question_category
from apps.evaluation.services.sufficiency_bridge import (
    get_answer_text_for_evaluation,
    resolve_answer_sufficiency,
)

logger = logging.getLogger("feedback_ai.session_evaluation")


def _try_record_ab_results(user_id: int, answer_id, evaluation, ai_result: dict) -> None:
    """활성 A/B 실험 전체에 평가 결과를 기록한다.

    - 활성 실험이 없으면 쿼리 1회로 단락.
    - 실패해도 예외를 전파하지 않는다 — 평가 트랜잭션과 격리.

    Args:
        user_id:    answer.session.user_id (BigInt, User.id).
        answer_id:  answer.id.
        evaluation: 방금 생성된 Evaluation 인스턴스.
        ai_result:  run_pipeline 반환값 (pipeline_tags/emotion_intent_score 이미 pop된 상태).
    """
    try:
        from apps.evaluation.ab_test_models import ABTestExperiment
        from apps.evaluation.services.ab_test_service import (
            get_or_create_assignment,
            record_ab_result,
        )

        active_exp_names = list(
            ABTestExperiment.objects.filter(status="active").values_list("name", flat=True)
        )
        if not active_exp_names:
            return

        # bei_total: situation+task+action+result score 합산
        bei = ai_result.get("bei_score", {})
        bei_total = sum(
            v.get("score", 0) if isinstance(v, dict) else 0
            for v in bei.values()
        )
        # grounding은 LLM이 숫자 점수를 주지 않으므로 is_grounded로 0/100 환산 (None 방지)
        _grounding = ai_result.get("score_detail", {}).get("grounding", {})
        _grounding_score = _grounding.get("grounding_score")
        if _grounding_score is None:
            _grounding_score = 100.0 if _grounding.get("is_grounded") else 0.0

        score_dict = {
            "final_score": evaluation.final_tech_score,
            "bei_total": bei_total,
            "cbi_score": ai_result.get("cbi_score", {}).get("score"),
            "grounding_score": _grounding_score,
            "speech_score": (
                ai_result.get("score_detail", {})
                .get("speech_delivery", {})
                .get("speech_score")
            ),
            "sbert_score": evaluation.sbert_db_similarity,
            # emotion_intent_score는 ai_result에서 이미 pop됐으므로 evaluation에서 참조.
            # 프롬프트(EVAL_EMOTION_INTENT_FORMAT_PROMPT)가 생성하는 키는 confidence_score다.
            "emotion_confidence": (
                evaluation.emotion_intent_score.get("confidence_score")
                if isinstance(evaluation.emotion_intent_score, dict)
                else None
            ),
        }

        for exp_name in active_exp_names:
            get_or_create_assignment(user_id, exp_name)
            record_ab_result(exp_name, user_id, answer_id, score_dict)

        logger.debug(
            "A/B 결과 기록 완료 (answer=%s, experiments=%s)", answer_id, active_exp_names
        )
    except Exception:
        logger.exception(
            "A/B 결과 기록 실패 (answer=%s) — 평가에는 영향 없음", answer_id
        )
        if getattr(settings, "DEBUG", False):
            raise  # 개발 환경에서는 즉시 확인할 수 있도록 예외를 전파한다


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
    # InterviewQuestion.question_category가 있으면 그 값을 우선 사용한다.
    # 현재 스키마처럼 필드가 없는 경우에도 evaluation 파트 내부 헬퍼로
    # 보수적으로 분류해 grounding/SBERT 실행 여부를 결정한다.
    question_type = resolve_question_category(answer)

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

    # E7.7 — A/B 프레임워크 연결
    _try_record_ab_results(
        user_id=answer.session.user_id,
        answer_id=answer.id,
        evaluation=evaluation,
        ai_result=ai_result,
    )

    return evaluation


def evaluate_session_answers(session, reevaluate=False):
    """세션의 모든 답변을 평가한다(미평가분 백필).

    멱등하며 답변별로 예외를 격리한다: 한 답변 평가가 실패해도
    나머지 답변의 평가는 계속 진행된다.

    Args:
        session: InterviewSession 인스턴스.
        reevaluate: True 이면 이미 평가된 답변도 재평가한다.

    Returns:
        {"evaluated": int, "skipped": int, "failed": int, "format_failed": int}
        ("format_failed"는 "failed"의 부분집합으로, LLM 응답 포맷 오류로 실패한 답변 수.)
    """
    stats = {"evaluated": 0, "skipped": 0, "failed": 0, "format_failed": 0}

    answers_qs = session.answers.select_related("question", "session__jd").all()
    # 답변별 Evaluation.exists() N+1을 제거: 평가 완료된 answer_id를 한 번에 조회해 set 비교.
    evaluated_answer_ids = set(
        Evaluation.objects.filter(answer__in=answers_qs).values_list("answer_id", flat=True)
    )

    for answer in answers_qs:
        already_evaluated = answer.id in evaluated_answer_ids
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
        except EvaluationFormatError:
            # LLM 응답 포맷이 재시도까지 소진하고도 깨진 경우: 부분 리포트 정책(#5)에 따라
            # 전체를 막지 않고 답변 단위로 격리한다. 일반 예외와 동일하게 failed로 카운트하되,
            # 포맷 오류는 format_failed로도 따로 집계해 리포트 메타데이터/프론트 배너에 노출한다.
            logger.exception(
                "Session evaluation format error for answer %s (session %s) — isolating (partial report)",
                getattr(answer, "id", "?"),
                getattr(session, "id", "?"),
            )
            stats["failed"] += 1
            stats["format_failed"] += 1
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
