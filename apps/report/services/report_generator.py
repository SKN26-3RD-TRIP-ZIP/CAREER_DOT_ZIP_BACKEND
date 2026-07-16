import logging
import re
from collections import Counter

from django.utils import timezone

from apps.evaluation.services.session_evaluation import evaluate_session_answers
from apps.evaluation.services.question_category import resolve_question_category
from apps.evaluation.services.sufficiency_bridge import get_answer_text_for_evaluation
from apps.report.services.improvement_suggester import generate_improvement_suggestions

logger = logging.getLogger("feedback_ai.report_generator")

# ============================================================================
# E7.10 -- 페르소나별 점수 가중치 및 피드백 설정
#
# DB 저장값은 common/choices.py INTERVIEW_PERSONA_CHOICES 기준:
#   "coach" / "practical" / "verifier"
# ※ "pressure"는 interview/migrations/0009에서 제거됨 (기존 데이터 → verifier 변환)
#
# ── 가중치 설계 원칙 ──────────────────────────────────────────────────────────
#
# 각 페르소나는 "면접에서 무엇을 판단하려 하는가"라는 핵심 질문을 가진다.
# 가중치는 그 질문에 대한 답을 가장 잘 설명하는 지표에 높게 배분한다.
#
# 지표별 성격:
#   BEI       경험을 얼마나 논리적으로 구조화해서 말하는가 (STAR 구조, 0~100)
#   CBI       문제해결 역량의 성숙도 레벨이 어느 수준인가 (Lv.1~4 환산, 0~100)
#   Grounding 기술 수치 근거를 실제로 제시했는가 (is_grounded 비율, 0~100 or None)
#   Speech    발화 전달력이 얼마나 안정적인가 (필러워드·휴지 감점, 최대 80)
#
# 중요도 수치 범위:
#   High        0.30 ~ 0.40
#   Medium-High 0.25 ~ 0.35
#   Medium      0.20 ~ 0.25
#   Low         0.10 ~ 0.20
#   Very Low    0.05 ~ 0.10
#
# ============================================================================
PERSONA_CONFIG: dict[str, dict] = {
    # ── 코치형: "이 사람은 성장할 수 있는가?" ──────────────────────────────
    # BEI  High(0.40): 경험에서 교훈을 추출하는 능력 = 성장 가능성의 직접 지표
    # CBI  Medium(0.25): 현재 레벨이 낮아도 괜찮지만, 현재 위치 파악은 필요
    # GRD  Low(0.15): 성장 단계 지원자에게 수치 실적보다 방향성·태도가 더 중요
    # SPE  Medium(0.20): 발화가 너무 불안하면 코칭 자체가 어려움, 기준은 낮게
    "coach": {
        "weights": {"bei": 0.40, "cbi": 0.25, "grounding": 0.15, "speech": 0.20},
        "label": "코치형",
        "intro": "성장 가능성과 학습 태도를 중심으로 평가한 결과입니다.",
        "strength_prefix": "앞으로의 성장 잠재력이 돋보이는 부분:",
        "weakness_prefix": "집중 훈련이 필요한 영역:",
        "closing_template": "꾸준한 연습을 통해 충분히 개선할 수 있는 영역이 확인되었습니다. 재도전을 적극 권장합니다.",
    },
    # ── 실전형: "이 사람을 지금 당장 현장에 투입할 수 있는가?" ──────────────
    # BEI  Medium-High(0.30): "행동"·"결과" 요소 위주로 중요, 구조보다 내용의 무게감
    # CBI  Medium(0.25): Lv.3 이상이어야 실무 투입 가능, Grounding이 더 직접적 지표
    # GRD  High(0.30): 수치·기술스택으로 증명 가능한 성과인가 = 현장 투입 가능성의 핵심
    # SPE  Low(0.15): 내용이 충분하면 발화는 부차적
    "practical": {
        "weights": {"bei": 0.30, "cbi": 0.25, "grounding": 0.30, "speech": 0.15},
        "label": "실전형",
        "intro": "실무 적합성과 기술 깊이를 최우선으로 평가한 결과입니다.",
        "strength_prefix": "실무에서 즉시 발휘 가능한 강점:",
        "weakness_prefix": "현장 투입 전 보완이 필요한 기술 영역:",
        "closing_template": "기술 스택 심화 학습과 수치 기반 성과 정리가 취업 경쟁력을 높이는 핵심입니다.",
    },
    # ── 검증형: "이 사람의 역량 주장이 실제인가?" ───────────────────────────
    # BEI  High(0.35): 경험이 논리적으로 일관되는가 = 진위 검증의 핵심 도구
    # CBI  High(0.35): 주장하는 역량 레벨이 실제 발화와 일치하는가
    # GRD  Medium(0.20): BEI·CBI로 이미 검증하므로 보조 지표 수준
    # SPE  Very Low(0.10): 역량 진위 검증에서 발화 습관은 가장 부차적
    "verifier": {
        "weights": {"bei": 0.35, "cbi": 0.35, "grounding": 0.20, "speech": 0.10},
        "label": "검증형",
        "intro": "역량 진위와 답변 일관성을 엄격히 검증한 결과입니다.",
        "strength_prefix": "신뢰 가능한 역량 근거가 확인된 항목:",
        "weakness_prefix": "검증 기준 미달로 보완이 필요한 항목:",
        "closing_template": "답변의 구체성과 일관성이 핵심 평가 기준입니다. 모호한 표현을 수치와 사례로 대체하세요.",
    },
}

# ── 가중치 합계 검증 ──────────────────────────────────────────────────────────
# 누군가 가중치를 수정할 때 합계가 1.0을 벗어나면 점수가 100점 만점을 초과하거나
# 과소 산정된다. 모듈 로드 시점에 한 번만 검증해 배포 전에 오류를 잡는다.
for _persona_name, _persona_cfg in PERSONA_CONFIG.items():
    _weight_sum = sum(_persona_cfg["weights"].values())
    assert abs(_weight_sum - 1.0) < 1e-6, (
        f"[PERSONA_CONFIG] '{_persona_name}' 페르소나 가중치 합계가 1.0이 아닙니다: "
        f"{_weight_sum:.4f} (항목: {_persona_cfg['weights']})"
    )

_DEFAULT_PERSONA_CONFIG = PERSONA_CONFIG["practical"]


def _get_persona_config(persona: str | None) -> dict:
    return PERSONA_CONFIG.get(persona or "", _DEFAULT_PERSONA_CONFIG)


def _apply_persona_weights(
    bei_avg: float,
    cbi_avg: float,
    grounding_avg: float | None,
    speech_avg: float,
    persona: str | None,
) -> float:
    cfg = _get_persona_config(persona)
    w = cfg["weights"]
    # option-C: grounding_avg가 None이면(기술 답변 없는 세션) 해당 가중치를
    # 제외하고 나머지 가중치를 정규화해 100점 만점 유지.
    if grounding_avg is None:
        active_weight = 1.0 - w["grounding"]
        if active_weight <= 0:
            active_weight = 1.0
        raw = (
            bei_avg * w["bei"]
            + cbi_avg * w["cbi"]
            + speech_avg * w["speech"]
        ) / active_weight
    else:
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


def _has_structured_bei_scores(bei: dict) -> bool:
    required_keys = ("situation", "task", "action", "result")
    return all(
        isinstance(bei.get(key), dict)
        and isinstance(bei[key].get("score"), (int, float))
        for key in required_keys
    )


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


def _tag_display(tag_name: str, desc_map: dict) -> str:
    """태그명 앞의 '[카테고리] ' 접두사를 제거하고 표시용 문자열을 반환한다."""
    raw = desc_map.get(tag_name) or tag_name
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", raw).strip()
    return cleaned or raw


# ── 집계 helper ──────────────────────────────────────────────────────────────

def _aggregate_scores(evaluated_answers: list) -> dict:
    """평가된 답변 목록에서 BEI·CBI·Speech·SBERT·Grounding 지표를 집계한다.

    Returns:
        {
            bei_situations, bei_tasks, bei_actions, bei_results,
            structured_bei_count,
            cbi_levels, cbi_scores,
            speech_scores, sbert_scores, technical_answer_scores,
            grounding_results, technical_answer_count,
            strength_counter, weakness_counter,
            strength_desc_map, weakness_desc_map,
        }
    """
    strength_counter: Counter = Counter()
    weakness_counter: Counter = Counter()
    strength_desc_map: dict[str, str] = {}
    weakness_desc_map: dict[str, str] = {}
    bei_situations, bei_tasks, bei_actions, bei_results = [], [], [], []
    structured_bei_count = 0
    cbi_levels: list = []
    cbi_scores: list = []
    speech_scores: list = []
    sbert_scores: list = []
    technical_answer_scores: list = []
    grounding_results: list = []
    technical_answer_count = 0

    for ans in evaluated_answers:
        eval_obj = ans.evaluation

        # 태그 집계
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

        # SBERT
        sbert_sims = [
            s for s in (
                getattr(eval_obj, "sbert_db_similarity", None),
                getattr(eval_obj, "sbert_readme_similarity", None),
            )
            if s is not None
        ]
        if sbert_sims:
            sbert_scores.append(sum(sbert_sims) / len(sbert_sims))

        # BEI
        bei = eval_obj.bei_score if isinstance(eval_obj.bei_score, dict) else {}
        if _has_structured_bei_scores(bei):
            structured_bei_count += 1
        bei_situations.append(get_score(bei.get("situation")))
        bei_tasks.append(get_score(bei.get("task")))
        bei_actions.append(get_score(bei.get("action")))
        bei_results.append(get_score(bei.get("result")))

        # CBI
        cbi = eval_obj.cbi_score if isinstance(eval_obj.cbi_score, dict) else {}
        if "assigned_level" in cbi:
            cbi_levels.append(cbi["assigned_level"])
        elif "level" in cbi:
            cbi_levels.append(cbi["level"])
        if "score" in cbi:
            cbi_scores.append(cbi["score"])

        # Speech
        score_detail = eval_obj.score_detail if isinstance(eval_obj.score_detail, dict) else {}
        speech_delivery = score_detail.get("speech_delivery", {})
        if speech_delivery.get("speech_score") is not None:
            speech_scores.append(speech_delivery["speech_score"])

        # Grounding (기술 질문만)
        # InterviewQuestion.question_category가 있으면 그 값을 사용하고,
        # 없으면 evaluation 파트의 호환 헬퍼로 분류한다.
        q_category = resolve_question_category(ans)
        if q_category == "technical":
            technical_answer_count += 1
            answer_score = getattr(eval_obj, "answer_score", None)
            if isinstance(answer_score, (int, float)):
                technical_answer_scores.append(answer_score)
            grounding_block = score_detail.get("grounding", {})
            if isinstance(grounding_block, dict) and "is_grounded" in grounding_block:
                grounding_results.append({
                    "is_grounded": bool(grounding_block.get("is_grounded")),
                    "grounding_applicable": grounding_block.get("grounding_applicable", True),
                })

    return {
        "bei_situations": bei_situations,
        "bei_tasks": bei_tasks,
        "bei_actions": bei_actions,
        "bei_results": bei_results,
        "structured_bei_count": structured_bei_count,
        "cbi_levels": cbi_levels,
        "cbi_scores": cbi_scores,
        "speech_scores": speech_scores,
        "sbert_scores": sbert_scores,
        "technical_answer_scores": technical_answer_scores,
        "grounding_results": grounding_results,
        "technical_answer_count": technical_answer_count,
        "strength_counter": strength_counter,
        "weakness_counter": weakness_counter,
        "strength_desc_map": strength_desc_map,
        "weakness_desc_map": weakness_desc_map,
    }


def _aggregate_speech_diagnostics(evaluated_answers: list) -> dict:
    """세션 전체 필러워드·휴지(E7.6) 진단 데이터를 집계한다."""
    total_filler_count = 0
    total_repetition_count = 0
    global_filler_words_counter: Counter = Counter()
    total_long_pause_count = 0
    pause_pattern_counter: Counter = Counter()
    answers_with_pause = 0

    for ans in evaluated_answers:
        filler_data = getattr(ans.evaluation, "filler_words", {}) or {}
        if isinstance(filler_data, dict):
            total_filler_count += filler_data.get("total", 0)
            total_repetition_count += filler_data.get("repetition_count", 0)
            counts = filler_data.get("counts", {})
            if isinstance(counts, dict):
                for word, cnt in counts.items():
                    global_filler_words_counter[word] += cnt

        pause_data = getattr(ans.evaluation, "pause_analysis", {}) or {}
        if isinstance(pause_data, dict) and pause_data:
            answers_with_pause += 1
            total_long_pause_count += pause_data.get("long_pause_count", 0)
            severity = pause_data.get("pause_severity")
            if severity and severity != "none":
                pause_pattern_counter[severity] += 1

    n = len(evaluated_answers)
    return {
        "total_filler_count": total_filler_count,
        "avg_fillers_per_answer": round(total_filler_count / n, 2) if n else 0,
        "total_repetition_count": total_repetition_count,
        "avg_repetitions_per_answer": round(total_repetition_count / n, 2) if n else 0,
        "filler_word_distribution": dict(global_filler_words_counter),
        "filler_words_counter": global_filler_words_counter,  # 요약 문구 생성용 Counter 객체
        "pause_summary": {
            "total_long_pause_count": total_long_pause_count,
            "avg_long_pause_per_answer": (
                round(total_long_pause_count / answers_with_pause, 2) if answers_with_pause else 0
            ),
            "severity_distribution": dict(pause_pattern_counter),
        },
    }


def _compute_avg_scores(agg: dict, n: int) -> tuple[float, float, float, float, dict]:
    """집계 데이터에서 평균 지표와 상세 통계를 계산한다.

    Returns:
        (bei_avg, cbi_avg, speech_avg, grounding_avg, detailed_stats)
        grounding_avg는 기술 답변이 없는 세션에서 None이 될 수 있다.
    """
    bei_avg = cbi_avg = speech_avg = 0.0
    detailed_stats: dict = {}

    if n > 0:
        bei_situations = agg["bei_situations"]
        bei_tasks      = agg["bei_tasks"]
        bei_actions    = agg["bei_actions"]
        bei_results    = agg["bei_results"]
        cbi_scores     = agg["cbi_scores"]
        cbi_levels     = agg["cbi_levels"]
        speech_scores  = agg["speech_scores"]

        avg_sit = round(sum(bei_situations) / n, 1)
        avg_tsk = round(sum(bei_tasks) / n, 1)
        avg_act = round(sum(bei_actions) / n, 1)
        avg_res = round(sum(bei_results) / n, 1)
        # bei_avg: 0~100 스케일(4요소 합) — 페르소나 가중치 입력용
        bei_avg    = round(avg_sit + avg_tsk + avg_act + avg_res, 1)
        cbi_avg    = round(sum(cbi_scores) / len(cbi_scores), 1) if cbi_scores else 0.0
        speech_avg = round(sum(speech_scores) / len(speech_scores), 1) if speech_scores else 0.0
        detailed_stats = {
            "bei_metrics": {
                "averages": {
                    "situation": avg_sit,
                    "task": avg_tsk,
                    "action": avg_act,
                    "result": avg_res,
                },
                # bei_element_avg: 0~25 스케일(요소 평균) — 상세 통계 표시용
                "element_total_avg": round((avg_sit + avg_tsk + avg_act + avg_res) / 4, 1),
            },
            "cbi_metrics": {
                "average_level": round(sum(cbi_levels) / len(cbi_levels), 1) if cbi_levels else 0,
                "average_score": cbi_avg,
            },
        }

    # E7 리뷰 #3 — grounding 지표: applicable한 답변 중 is_grounded 비율 × 100.
    # option-C: 기술 답변이 없는 세션(인성면접 전용)은 None → 페르소나 가중치에서 제외.
    technical_answer_count = agg["technical_answer_count"]
    grounding_results      = agg["grounding_results"]
    if technical_answer_count == 0:
        grounding_avg = None
    else:
        applicable = [g for g in grounding_results if g.get("grounding_applicable", True)]
        grounding_avg = (
            round(sum(1 for g in applicable if g.get("is_grounded")) / len(applicable) * 100, 1)
            if applicable
            else None
        )

    return bei_avg, cbi_avg, speech_avg, grounding_avg, detailed_stats


def _build_summary_text(
    strength_counter: Counter,
    weakness_counter: Counter,
    strength_desc_map: dict,
    weakness_desc_map: dict,
    speech_diag: dict,
) -> tuple[list[str], list[str]]:
    """세션 요약 문구와 추천 문구를 생성한다.

    Returns:
        (summary_text_parts, recommendations)
    """
    summary_text_parts: list[str] = []
    recommendations: list[str] = []

    if strength_counter:
        top_s_name = strength_counter.most_common(1)[0][0]
        summary_text_parts.append(
            f"이번 세션에서 가장 강력하게 발휘된 역량은 '{_tag_display(top_s_name, strength_desc_map)}' 입니다."
        )
    if weakness_counter:
        top_w_name = weakness_counter.most_common(1)[0][0]
        summary_text_parts.append(
            f"가장 빈번하게 노출된 보완점은 '{_tag_display(top_w_name, weakness_desc_map)}' 항목으로 확인됩니다."
        )

    total_filler_count      = speech_diag["total_filler_count"]
    avg_fillers_per_answer  = speech_diag["avg_fillers_per_answer"]
    filler_words_counter    = speech_diag["filler_words_counter"]

    if total_filler_count > 0:
        most_common_fillers = [word for word, _ in filler_words_counter.most_common(2)]
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

    return summary_text_parts, recommendations


def _build_question_breakdown(evaluated_answers: list) -> tuple[list[dict], list[dict]]:
    """질문별 점수·개선 액션·LLM 입력 데이터를 생성한다.

    Returns:
        (question_breakdown, suggester_inputs)
        question_breakdown: 프론트엔드로 내려가는 질문별 평가 목록 (improvement_action은 폴백값)
        suggester_inputs:   improvement_suggester LLM 배치 호출용 입력 목록
    """
    question_breakdown: list[dict] = []
    suggester_inputs: list[dict] = []

    for ans in evaluated_answers:
        q        = ans.question
        eval_obj = ans.evaluation
        q_score  = getattr(eval_obj, "answer_score", None)
        wmaps    = list(ans.weakness_mappings.all())

        # 폴백용 템플릿 문구 — 최우선순위 약점 태그의 reason/description
        fallback_action = ""
        weakness_descs: list[str] = []
        if wmaps:
            ordered = sorted(wmaps, key=lambda m: getattr(m, "priority_rank", 99) or 99)
            top_wm = ordered[0]
            fallback_action = top_wm.reason or (
                (top_wm.weakness_tag.description or "") if top_wm.weakness_tag else ""
            )
            for m in ordered:
                raw_desc = m.reason or (
                    (m.weakness_tag.description or "") if m.weakness_tag else ""
                )
                desc = str(raw_desc).strip()
                if desc and desc not in weakness_descs:
                    weakness_descs.append(desc)

        # grounding 누락 항목 추출 (LLM 컨텍스트 보강용)
        sd = eval_obj.score_detail if isinstance(eval_obj.score_detail, dict) else {}
        grounding_block = sd.get("grounding", {}) if isinstance(sd.get("grounding"), dict) else {}
        grounding_gaps = [
            label for label, key in (
                ("기술스택 근거", "tech_stack"),
                ("개선 전 수치", "before_metric"),
                ("개선 후 수치", "after_metric"),
            )
            if str(grounding_block.get(key, "")).strip() in ("", "확인 불가")
        ]

        qid = str(q.id)
        question_breakdown.append({
            "question_id": qid,
            "answer_id": str(ans.id),
            "has_audio": bool(ans.audio_key),
            "order": q.order_index,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "improvement_action": fallback_action,  # LLM 성공 시 아래에서 덮어씀
            "score": q_score if q_score is not None else 0,
        })

        try:
            answer_text = get_answer_text_for_evaluation(ans)
        except Exception:
            answer_text = ""

        suggester_inputs.append({
            "question_id": qid,
            "question_text": q.question_text,
            "answer_text": answer_text,
            "weaknesses": weakness_descs,
            "grounding_gaps": grounding_gaps,
            "score": q_score if q_score is not None else 0,
        })

    return question_breakdown, suggester_inputs


# ── 공개 진입점 ──────────────────────────────────────────────────────────────

def generate_final_report(session):
    """FinalReport.summary JSONB 페이로드를 생성한다.

    구조: evaluation_metadata / score_summary / score_detail / dynamically_triggered_tags
    """
    # 1. 미평가 답변 백필
    # 부분 리포트 정책(#5): 답변 단위 LLM 포맷 오류(EvaluationFormatError)는 백필 내부에서
    # 격리되어 failed/format_failed로 집계된다. 전체 리포트를 막지 않는다.
    backfill_stats = {}
    try:
        backfill_stats = evaluate_session_answers(session) or {}
    except Exception:
        logger.exception(
            "evaluate_session_answers backfill failed for session %s",
            getattr(session, "id", "?"),
        )

    # 2. 데이터 로드
    answers = session.answers.all().select_related("evaluation", "question", "session").prefetch_related(
        "strength_mappings__strength_tag",
        "weakness_mappings__weakness_tag",
    )
    questions     = list(session.questions.all())
    answers_list  = list(answers)
    evaluated_answers = [
        ans for ans in answers_list
        if hasattr(ans, "evaluation") and ans.evaluation is not None
    ]
    n = len(evaluated_answers)

    # 단순 평균 overall_score (페르소나 가중치 미적용 fallback)
    final_scores  = [
        ans.evaluation.answer_score
        for ans in evaluated_answers
        if getattr(ans.evaluation, "answer_score", None) is not None
    ]
    overall_score = round(sum(final_scores) / len(final_scores)) if final_scores else 0

    # 3. 지표 집계
    agg        = _aggregate_scores(evaluated_answers)
    speech_diag = _aggregate_speech_diagnostics(evaluated_answers)

    # 4. 평균 지표 계산
    bei_avg, cbi_avg, speech_avg, grounding_avg, detailed_stats = _compute_avg_scores(agg, n)

    sbert_scores          = agg["sbert_scores"]
    technical_answer_scores = agg["technical_answer_scores"]
    technical_answer_count = agg["technical_answer_count"]
    technical_avg = (
        round((sum(sbert_scores) / len(sbert_scores)) * 100, 1)
        if sbert_scores
        else (
            round(sum(technical_answer_scores) / len(technical_answer_scores), 1)
            if technical_answer_scores
            else (0.0 if technical_answer_count > 0 else None)
        )
    )

    # 5. 페르소나 가중치 적용 overall_score 재산출 (E7.10)
    persona     = getattr(session, "persona", None)
    persona_cfg = _get_persona_config(persona)
    persona_weighted_score = _apply_persona_weights(
        bei_avg=bei_avg,
        cbi_avg=cbi_avg,
        grounding_avg=grounding_avg,
        speech_avg=speech_avg,
        persona=persona,
    )
    has_grounding_inputs = (
        technical_answer_count == 0
        or len(agg["grounding_results"]) == technical_answer_count
    )
    has_persona_weight_inputs = (
        n > 0
        and agg["structured_bei_count"] == n
        and len(agg["cbi_scores"]) == n
        and len(agg["speech_scores"]) == n
        and has_grounding_inputs
    )
    overall_score = persona_weighted_score if has_persona_weight_inputs else overall_score

    # 6. 태그 집계 및 요약 문구 생성
    top_strength_names = [name for name, _ in agg["strength_counter"].most_common(5)]
    top_weakness_names = [name for name, _ in agg["weakness_counter"].most_common(5)]
    strength_tags = _aggregate_tag_objects(evaluated_answers, "strength_mappings", "strength_tag")
    weakness_tags = _aggregate_tag_objects(evaluated_answers, "weakness_mappings", "weakness_tag")

    summary_text_parts, recommendations = _build_summary_text(
        agg["strength_counter"],
        agg["weakness_counter"],
        agg["strength_desc_map"],
        agg["weakness_desc_map"],
        speech_diag,
    )

    # 7. 질문별 개선 액션 생성
    # 1차: 약점 태그 템플릿 폴백, 2차: LLM 배치 호출로 덮어씀
    # LLM 실패/mock 시 템플릿 폴백 유지 → 리포트는 항상 생성된다.
    question_breakdown, suggester_inputs = _build_question_breakdown(evaluated_answers)
    llm_suggestions = generate_improvement_suggestions(suggester_inputs)
    if llm_suggestions:
        for item in question_breakdown:
            suggestion = llm_suggestions.get(item["question_id"])
            if suggestion:
                item["improvement_action"] = suggestion
    question_breakdown.sort(key=lambda item: item["order"])

    # 8. 페르소나 피드백 구성
    persona_feedback = {
        "persona": persona or "practical",
        "persona_label": persona_cfg["label"],
        "intro": persona_cfg["intro"],
        "strength_prefix": persona_cfg["strength_prefix"],
        "weakness_prefix": persona_cfg["weakness_prefix"],
        "closing": persona_cfg["closing_template"],
        "persona_weights": persona_cfg["weights"],
    }

    return {
        "evaluation_metadata": {
            "session_id": str(session.id),
            "persona_type": session.persona,
            "interview_mode": session.interview_mode,
            "interview_type": session.interview_type,
            "question_count": len(questions),
            "answer_count": len(answers_list),
            "evaluated_answer_count": n,
            # 부분 리포트(#5): 채점되지 않은 답변 수. answer_count - evaluated_answer_count로
            # 항상 정확히 산출(캐시/재생성 시점과 무관). 프론트 경고 배너의 기준값.
            "unscored_answer_count": max(len(answers_list) - n, 0),
            # 이번 백필에서 LLM 응답 포맷 오류로 실패한 답변 수(진단용 보조 지표).
            "format_failed_answer_count": int(backfill_stats.get("format_failed", 0) or 0),
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
                "total_filler_count": speech_diag["total_filler_count"],
                "avg_fillers_per_answer": speech_diag["avg_fillers_per_answer"],
                "total_repetition_count": speech_diag["total_repetition_count"],
                "avg_repetitions_per_answer": speech_diag["avg_repetitions_per_answer"],
                "filler_word_distribution": speech_diag["filler_word_distribution"],
                "pause_summary": speech_diag["pause_summary"],
            },
        },
        "dynamically_triggered_tags": {
            "strength_tags": strength_tags,
            "weakness_tags": weakness_tags,
        },
    }
