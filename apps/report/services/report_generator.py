import logging
import re
from collections import Counter

from django.utils import timezone

from apps.evaluation.services.session_evaluation import evaluate_session_answers

logger = logging.getLogger("feedback_ai.report_generator")

# E7.10 -- 페르소나별 점수 가중치 및 피드백 설정
# DB 저장값은 common/choices.py INTERVIEW_PERSONA_CHOICES 기준:
#   "coach" / "practical" / "verifier"
# ※ "pressure"는 interview/migrations/0009에서 제거됨 (기존 데이터 → verifier 변환)
PERSONA_CONFIG: dict[str, dict] = {
    "coach": {
        "weights": {"bei": 0.40, "cbi": 0.25, "grounding": 0.15, "speech": 0.20},
        "label": "코치형",
        "intro": "성장 가능성과 학습 태도를 중심으로 평가한 결과입니다.",
        "strength_prefix": "앞으로의 성장 잠재력이 돋보이는 부분:",
        "weakness_prefix": "집중 훈련이 필요한 영역:",
        "closing_template": "꾸준한 연습을 통해 충분히 개선할 수 있는 영역이 확인되었습니다. 재도전을 적극 권장합니다.",
    },
    "practical": {
        "weights": {"bei": 0.30, "cbi": 0.25, "grounding": 0.30, "speech": 0.15},
        "label": "실전형",
        "intro": "실무 적합성과 기술 깊이를 최우선으로 평가한 결과입니다.",
        "strength_prefix": "실무에서 즉시 발휘 가능한 강점:",
        "weakness_prefix": "현장 투입 전 보완이 필요한 기술 영역:",
        "closing_template": "기술 스택 심화 학습과 수치 기반 성과 정리가 취업 경쟁력을 높이는 핵심입니다.",
    },
    "verifier": {
        "weights": {"bei": 0.35, "cbi": 0.35, "grounding": 0.20, "speech": 0.10},
        "label": "검증형",
        "intro": "역량 진위와 답변 일관성을 엄격히 검증한 결과입니다.",
        "strength_prefix": "신뢰 가능한 역량 근거가 확인된 항목:",
        "weakness_prefix": "검증 기준 미달로 보완이 필요한 항목:",
        "closing_template": "답변의 구체성과 일관성이 핵심 평가 기준입니다. 모호한 표현을 수치와 사례로 대체하세요.",
    },
}

_DEFAULT_PERSONA_CONFIG = PERSONA_CONFIG["practical"]


def _get_persona_config(persona: str | None) -> dict:
    return PERSONA_CONFIG.get(persona or "", _DEFAULT_PERSONA_CONFIG)


def _apply_persona_weights(
    bei_avg: float,
    cbi_avg: float,
    grounding_avg: float,
    speech_avg: float,
    persona: str | None,
) -> float:
    cfg = _get_persona_config(persona)
    w = cfg["weights"]
    raw = (
        bei_avg * w["bei"]
        + cbi_avg * w["cbi"]
        + grounding_avg * w["grounding"]
        + speech_avg * w["speech"]
    )
    return min(round(raw, 1), 100.0)


def get_score(value):
    if isinstance(value, dict):
        return value.get("score", 0)
    return value or 0


def _aggregate_tag_objects(evaluated_answers, mapping_attr, tag_attr):
    tag_map = {}
    for answer in evaluated_answers:
        for mapping in getattr(answer, mapping_attr).all():
            tag = getattr(mapping, tag_attr)
            name = tag.tag_name
            if name not in tag_map:
                tag_map[name] = {
                    "tag_name": name,
                    "description": mapping.reason or tag.description or "",
                    "trigger_signal": getattr(mapping, "trigger_signal_log", None) or mapping.reason or "",
                    "count": 0,
                }
            tag_map[name]["count"] += 1
    ranked = sorted(tag_map.values(), key=lambda item: (-item["count"], item["tag_name"]))
    for item in ranked:
        item.pop("count", None)
    return ranked[:5]


def generate_final_report(session):
    """FinalReport.summary JSONB 페이로드를 생성한다.

    구조: evaluation_metadata / score_summary / score_detail / dynamically_triggered_tags
    """
    try:
        evaluate_session_answers(session)
    except Exception:
        logger.exception(
            "evaluate_session_answers backfill failed for session %s",
            getattr(session, "id", "?"),
        )

    answers = session.answers.all().select_related("evaluation", "question").prefetch_related(
        "strength_mappings__strength_tag",
        "weakness_mappings__weakness_tag",
    )

    questions = list(session.questions.all())
    answers_list = list(answers)
    evaluated_answers = [
        ans for ans in answers_list
        if hasattr(ans, "evaluation") and ans.evaluation is not None
    ]

    final_scores = [
        ans.evaluation.final_tech_score
        for ans in evaluated_answers
        if getattr(ans.evaluation, "final_tech_score", None) is not None
    ]
    overall_score = round(sum(final_scores) / len(final_scores)) if final_scores else 0

    strength_counter: Counter = Counter()
    weakness_counter: Counter = Counter()
    strength_desc_map: dict[str, str] = {}
    weakness_desc_map: dict[str, str] = {}
    bei_situations, bei_tasks, bei_actions, bei_results = [], [], [], []
    cbi_levels: list = []
    cbi_scores: list = []
    speech_scores: list = []
    sbert_scores: list = []
    grounding_flags: list = []   # E7 리뷰 #3 — 답변별 is_grounded 수집

    for ans in evaluated_answers:
        eval_obj = ans.evaluation

        for sm in ans.strength_mappings.all():
            name = sm.strength_tag.tag_name
            strength_counter[name] += 1
            if name not in strength_desc_map:
                strength_desc_map[name] = sm.strength_tag.description or name
        for wm in ans.weakness_mappings.all():
            name = wm.weakness_tag.tag_name
            weakness_counter[name] += 1
            if name not in weakness_desc_map:
                weakness_desc_map[name] = wm.weakness_tag.description or name

        sbert_sims = [
            s for s in (
                getattr(eval_obj, "sbert_db_similarity", None),
                getattr(eval_obj, "sbert_readme_similarity", None),
            )
            if s is not None
        ]
        if sbert_sims:
            sbert_scores.append(sum(sbert_sims) / len(sbert_sims))

        bei = eval_obj.bei_score if isinstance(eval_obj.bei_score, dict) else {}
        bei_situations.append(get_score(bei.get("situation")))
        bei_tasks.append(get_score(bei.get("task")))
        bei_actions.append(get_score(bei.get("action")))
        bei_results.append(get_score(bei.get("result")))

        cbi = eval_obj.cbi_score if isinstance(eval_obj.cbi_score, dict) else {}
        if "assigned_level" in cbi:
            cbi_levels.append(cbi["assigned_level"])
        elif "level" in cbi:
            cbi_levels.append(cbi["level"])
        if "score" in cbi:
            cbi_scores.append(cbi["score"])

        score_detail = eval_obj.score_detail if isinstance(eval_obj.score_detail, dict) else {}
        speech_delivery = score_detail.get("speech_delivery", {})
        if speech_delivery.get("speech_score") is not None:
            speech_scores.append(speech_delivery["speech_score"])

        grounding_block = score_detail.get("grounding", {})
        if isinstance(grounding_block, dict) and "is_grounded" in grounding_block:
            grounding_flags.append(bool(grounding_block.get("is_grounded")))

    top_strength_names = [name for name, _ in strength_counter.most_common(5)]
    top_weakness_names = [name for name, _ in weakness_counter.most_common(5)]

    total_filler_count = 0
    global_filler_words_counter: Counter = Counter()
    for ans in evaluated_answers:
        filler_data = getattr(ans.evaluation, "filler_words", {}) or {}
        if isinstance(filler_data, dict):
            total_filler_count += filler_data.get("total", 0)
            counts = filler_data.get("counts", {})
            if isinstance(counts, dict):
                for word, cnt in counts.items():
                    global_filler_words_counter[word] += cnt

    n = len(evaluated_answers)
    avg_fillers_per_answer = round(total_filler_count / n, 2) if n else 0

    def _tag_display(tag_name: str, desc_map: dict) -> str:
        raw = desc_map.get(tag_name) or tag_name
        cleaned = re.sub(r"^\[[^\]]+\]\s*", "", raw).strip()
        return cleaned or raw

    recommendations: list[str] = []
    summary_text_parts: list[str] = []
    if strength_counter:
        top_s_name = strength_counter.most_common(1)[0][0]
        top_s_label = _tag_display(top_s_name, strength_desc_map)
        summary_text_parts.append(
            f"이번 세션에서 가장 강력하게 발휘된 역량은 '{top_s_label}' 입니다."
        )
    if weakness_counter:
        top_w_name = weakness_counter.most_common(1)[0][0]
        top_w_label = _tag_display(top_w_name, weakness_desc_map)
        summary_text_parts.append(
            f"가장 빈번하게 노출된 보완점은 '{top_w_label}' 항목으로 확인됩니다."
        )
    if total_filler_count > 0:
        most_common_fillers = [word for word, _ in global_filler_words_counter.most_common(2)]
        filler_str = ", ".join([f"'{w}'" for w in most_common_fillers])
        summary_text_parts.append(f"전체 면접 중 총 {total_filler_count}회의 습관어가 감지되었습니다.")
        if avg_fillers_per_answer >= 3.0:
            recommendations.append(
                f"답변 과정에서 {filler_str} 등의 추임새가 자주 반복됩니다. "
                "생각을 정리할 때 1~2초 의도적 pause 연습을 권장합니다."
            )
        else:
            recommendations.append(
                f"주로 감지되는 표현은 {filler_str} 입니다. 실전에서도 현재 발화 페이스를 유지하세요."
            )
    else:
        summary_text_parts.append("비유창성 언어가 거의 발견되지 않은 정제된 발화 습관을 보여주었습니다.")

    if not recommendations:
        recommendations.append("세션 상세 답변의 꼬리질문 분석 내용을 점검해 보세요.")

    detailed_stats: dict = {}
    # bei_avg: 0~100 스케일(4요소 합) — score_summary 지표 및 페르소나 가중치 입력용.
    #          cbi_avg / grounding_avg / speech_avg 와 스케일을 일치시킨다.
    # bei_element_avg: 0~25 스케일(요소 평균) — 상세 통계 표시용.
    bei_avg = cbi_avg = speech_avg = 0.0
    bei_element_avg = 0.0
    if n > 0:
        avg_sit = round(sum(bei_situations) / n, 1)
        avg_tsk = round(sum(bei_tasks) / n, 1)
        avg_act = round(sum(bei_actions) / n, 1)
        avg_res = round(sum(bei_results) / n, 1)
        bei_element_avg = round((avg_sit + avg_tsk + avg_act + avg_res) / 4, 1)  # 0~25
        bei_avg = round(avg_sit + avg_tsk + avg_act + avg_res, 1)                # 0~100
        cbi_avg = round(sum(cbi_scores) / len(cbi_scores), 1) if cbi_scores else 0.0
        speech_avg = round(sum(speech_scores) / len(speech_scores), 1) if speech_scores else 0.0
        detailed_stats = {
            "bei_metrics": {
                "averages": {
                    "situation": avg_sit,
                    "task": avg_tsk,
                    "action": avg_act,
                    "result": avg_res,
                },
                "element_total_avg": bei_element_avg,
            },
            "cbi_metrics": {
                "average_level": round(sum(cbi_levels) / len(cbi_levels), 1) if cbi_levels else 0,
                "average_score": cbi_avg,
            },
        }

    # E7 리뷰 #3 — 실제 grounding 지표: is_grounded 비율 × 100.
    # (기존엔 final_tech_score 평균을 grounding_score로 잘못 노출하고 있었음)
    grounding_avg = round(sum(grounding_flags) / len(grounding_flags) * 100, 1) if grounding_flags else 0.0
    technical_avg = round((sum(sbert_scores) / len(sbert_scores)) * 100, 1) if sbert_scores else 0.0
    strength_tags = _aggregate_tag_objects(evaluated_answers, "strength_mappings", "strength_tag")
    weakness_tags = _aggregate_tag_objects(evaluated_answers, "weakness_mappings", "weakness_tag")

    # E7.10: 페르소나 가중치 적용 overall_score 재산출
    persona = getattr(session, "persona", None)
    persona_cfg = _get_persona_config(persona)
    persona_weighted_score = _apply_persona_weights(
        bei_avg=bei_avg,
        cbi_avg=cbi_avg,
        grounding_avg=grounding_avg,
        speech_avg=speech_avg,
        persona=persona,
    )
    overall_score = persona_weighted_score if n > 0 else overall_score

    persona_feedback = {
        "persona": persona or "practical",
        "persona_label": persona_cfg["label"],
        "intro": persona_cfg["intro"],
        "strength_prefix": persona_cfg["strength_prefix"],
        "weakness_prefix": persona_cfg["weakness_prefix"],
        "closing": persona_cfg["closing_template"],
        "persona_weights": persona_cfg["weights"],
    }

    question_breakdown: list[dict] = []
    for ans in evaluated_answers:
        q = ans.question
        eval_obj = ans.evaluation
        q_score = getattr(eval_obj, "final_tech_score", None)
        wmaps = list(ans.weakness_mappings.all())
        improvement_action = ""
        if wmaps:
            top_wm = sorted(wmaps, key=lambda m: getattr(m, "priority_rank", 99) or 99)[0]
            improvement_action = top_wm.reason or (
                top_wm.weakness_tag.description if top_wm.weakness_tag else ""
            )
        question_breakdown.append({
            "question_id": str(q.id),
            "order": q.order_index,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "improvement_action": improvement_action,
            "score": q_score if q_score is not None else 0,
        })
    question_breakdown.sort(key=lambda item: item["order"])

    return {
        "evaluation_metadata": {
            "session_id": str(session.id),
            "persona_type": session.persona,
            "interview_mode": session.interview_mode,
            "interview_type": session.interview_type,
            "question_count": len(questions),
            "answer_count": len(answers_list),
            "evaluated_answer_count": n,
            "calculated_at": timezone.now().isoformat(),
            "summary_text": (
                " ".join(summary_text_parts)
                if summary_text_parts
                else "세션 데이터 기반으로 최종 리포트가 생성되었습니다."
            ),
        },
        "score_summary": {
            "overall_score": overall_score,
            "metrics": {
                "bei_logic_score": bei_avg,
                "cbi_competency_score": cbi_avg,
                "grounding_score": grounding_avg,
                "speech_delivery_score": speech_avg,
                "technical_score": technical_avg,
            },
            "persona_feedback": persona_feedback,
        },
        "score_detail": {
            "strength": top_strength_names or ["리포트 생성 기본 요건을 충족했습니다."],
            "weakness": top_weakness_names or (
                ["전반적인 답변 구조의 일관성 확인이 필요합니다."] if len(answers_list) < 3 else []
            ),
            "improvement": recommendations,
            "questions": question_breakdown,
            "statistics": detailed_stats,
            "speech_diagnostics": {
                "total_filler_count": total_filler_count,
                "avg_fillers_per_answer": avg_fillers_per_answer,
                "filler_word_distribution": dict(global_filler_words_counter),
            },
        },
        "dynamically_triggered_tags": {
            "strength_tags": strength_tags,
            "weakness_tags": weakness_tags,
        },
    }
