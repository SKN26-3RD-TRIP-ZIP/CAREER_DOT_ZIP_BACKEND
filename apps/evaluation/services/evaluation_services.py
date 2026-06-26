import logging
import time
from collections import Counter
from datetime import datetime
from kiwipiepy import Kiwi
from django.conf import settings

# 💡 동기식으로 매핑된 기존 파일 및 외부 유틸 반입
from apps.evaluation.evaluation_chains import (
    eval_llm_chains_parallel_with_emotion,
    eval_llm_chains_competency_emotion,
)
from apps.evaluation.utils.tag_router import route_deterministic_tags

# 💡 SPEECH 기본값 단일 소스(SSOT). speech 점수 + E7.6 휴지 파라미터를 한 dict에 모은다.
# 과거에는 모듈 폴백 dict(BASE_SCORE=80)와 _calculate_speech_score의 인라인
# .get(..., 100.0) 기본값이 따로 놀아, settings.SPEECH_CONFIG가 일부 키만 정의하면
# 의도(80 상한)와 다른 100이 적용되는 불일치가 있었다. 이제 모든 기본값을 여기서만 관리한다.
_SPEECH_DEFAULTS = {
    "BASE_SCORE": 80.0,   # 완벽한 전달력도 80 상한
    "FILLER_PENALTY_PER_COUNT": 5.0,
    "FLOOR_SCORE": 20.0,
    "EXCESSIVE_FILLER_LIMIT": 6,
    # E7.6 휴지 파라미터
    "SPEECH_RATE_WORDS_PER_SEC": 3.0,
    "PAUSE_DURATION_SEC": 3.0,
    "PAUSE_RATIO_THRESHOLD": 0.30,
    "PAUSE_RATIO_PENALTY_SCALE": 50.0,
    "PAUSE_SEVERITY_PENALTY": {
        "none": 0.0, "minimal": 0.0, "moderate": 5.0, "high": 12.0, "critical": 22.0,
    },
    "PAUSE_SEVERITY_THRESHOLDS": {"minimal": 1, "moderate": 3, "high": 6},
}

# settings.SPEECH_CONFIG가 없으면 통째로 기본값 사용.
SPEECH_CONFIG = getattr(settings, "SPEECH_CONFIG", _SPEECH_DEFAULTS)


def _cfg(key):
    """SPEECH_CONFIG에서 값을 읽되, 키 누락 시 _SPEECH_DEFAULTS로 폴백(단일 소스)."""
    return SPEECH_CONFIG[key] if key in SPEECH_CONFIG else _SPEECH_DEFAULTS[key]

# 로거 정의
logger = logging.getLogger("feedback_ai.evaluation_service")

kiwi = Kiwi()
# 추임새(필러)로 셀 단어. "사실"·"이제"는 정상 어휘로 쓰이는 빈도가 높아(추임새로서의
# precision이 낮아) 오탐을 막기 위해 제외한다.
FILLER_WORDS = ["어", "음", "그니까", "그러니까", "저기"]
SINGLE_SYLLABLE_FILLER_TAGS = {"IC"}

# 근접 반복 탐지 윈도우(토큰 수). 동일 content 토큰이 이 범위 안에서 재등장하면 1회 반복으로
# 카운트한다. 말 더듬/즉시 반복 같은 비유창성을 잡되 멀리 떨어진 주제어 반복은 제외하도록 작게 둔다.
REPETITION_WINDOW = 3

# LLM이 반환하는 정성 점수의 유효 범위. 모델이 범위를 벗어난 값을 주더라도 하위 집계
# (report_generator의 bei_avg 4요소 합산 등)와 사용자 노출 지표가 정의역을 넘지 않도록
# 수집 지점(_extract_qualitative_scores)에서 클램핑한다. (E 리뷰 #1)
BEI_COMPONENT_SCORE_MAX = 25   # STAR 각 요소(situation/task/action/result): 0~25
CBI_SCORE_MAX = 100            # CBI 환산 점수: 0~100

# 이 글자 수(공백 제외) 미만의 답변은 LLM 평가가 의미 없으므로 호출을 생략하고 0점 처리한다.
# (빈 답변/오타 한두 글자 등으로 OpenAI 비용·지연을 낭비하지 않기 위함. settings로 조정 가능)
MIN_ANSWER_CHARS_FOR_LLM = getattr(settings, "MIN_ANSWER_CHARS_FOR_LLM", 5)


def _empty_llm_results() -> tuple[dict, dict, dict]:
    """빈/초단문 답변용 LLM 결과 스텁 (grounding / competency / emotion_intent)."""
    grounding = {
        "tech_stack": None,
        "before_metric": None,
        "after_metric": None,
        "is_grounded": False,
        "grounding_applicable": False,
    }
    competency = {
        "bei_star": {
            k: {"desc": "", "score": 0}
            for k in ("situation", "task", "action", "result")
        },
        "cbi_competency": {"assigned_level": 1, "score": 0, "evidence_sentence": ""},
        "llm_weakness_tags": [],
    }
    emotion = {
        "emotion_labels": {},
        "competency_intent_labels": {},
        "dominant_emotion": None,
        "dominant_competency": None,
        "confidence_score": 0.0,
    }
    return grounding, competency, emotion


def grounding_to_score(grounding: dict | None) -> float:
    """근거 충족 여부를 0~100 점수로 환산하는 단일 정의(SSOT).

    grounding은 LLM이 boolean(is_grounded)만 주고 숫자 점수를 주지 않으므로
    충족=100.0 / 미충족=0.0으로 환산한다. (이미 숫자 grounding_score가 있으면 그대로 사용)

    이 함수가 grounding_score의 유일한 정의다. 리포트 레벨 metrics.grounding_score(%)는
    applicable한 답변들에 대해 이 함수 결과를 평균낸 값과 같다(=근거 충족률 %).
    A/B 기록(_try_record_ab_results)도 반드시 이 함수를 통해 환산해 의미를 일치시킨다.
    """
    if not isinstance(grounding, dict):
        return 0.0
    raw = grounding.get("grounding_score")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    return 100.0 if grounding.get("is_grounded") else 0.0


def _clamp_score(value, lo, hi):
    """LLM 점수를 [lo, hi]로 제한한다.

    Returns:
        (clamped, was_adjusted). 숫자 변환 실패는 lo로 폴백하며 was_adjusted=True.
        범위 내 값은 정수면 정수로 유지(저장 JSON 일관성), 아니면 소수 1자리 반올림.
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return lo, True
    if num < lo:
        return lo, True
    if num > hi:
        return hi, True
    return (int(num) if num.is_integer() else round(num, 1)), False


class EvaluationService:

    @staticmethod
    def analyze_dysfluency_local(stt_text: str, long_pause_count: int = 0) -> dict:
        """[Task A] 로컬 비유창성 분석 (원본 알고리즘 보존 + E7.6 휴지 패턴 고도화)"""
        logger.info("=== [Task A] 로컬 비유창성 분석 시작 ===")
        start_time = time.time()

        # 형태소 토큰을 먼저 산출 — 단음절 필러의 부분문자열 오탐(예: "들어","어렵다",
        # "마음","처음")을 막기 위해 토큰 경계 기준으로 카운트한다.
        kiwi_tokens = list(kiwi.tokenize(stt_text))
        tokens = [token.form for token in kiwi_tokens]
        token_counter = Counter(tokens)

        filler_counts = {}
        total_filler = 0

        for word in FILLER_WORDS:
            if len(word) == 1:
                # 단음절 필러("어", "음")는 독립 감탄사(IC)인 경우만 집계한다.
                count = sum(
                    1
                    for token in kiwi_tokens
                    if token.form == word
                    and token.tag in SINGLE_SYLLABLE_FILLER_TAGS
                )
            else:
                # 다음절 필러는 형태소 토큰 완전 일치로 집계한다.
                count = token_counter.get(word, 0)

            if count > 0:
                filler_counts[word] = count
                total_filler += count

        # 근접 반복 탐지: 길이 2자 이상 content 토큰이 바로 뒤 REPETITION_WINDOW 범위 안에
        # 다시 등장하면 1회 반복으로 기록. (기존엔 i, i+1 인접 중복만 잡아 '음... 그 그 그런'처럼
        # 한두 토큰 떨어진 더듬/반복을 놓쳤다.)
        repetition_scans = []
        for i, tok in enumerate(tokens):
            if len(tok) < 2:
                continue
            if tok in tokens[i + 1 : i + 1 + REPETITION_WINDOW]:
                repetition_scans.append(tok)
        repetition_count = len(repetition_scans)

        # ── E7.6 — 휴지 패턴 고도화 ──────────────────────────────────
        # word_count 기반 추정 발화 시간: 한국어 평균 발화속도 ≈ 3단어/초
        word_count = len(stt_text.split())
        speech_rate = _cfg("SPEECH_RATE_WORDS_PER_SEC")
        estimated_speech_duration_sec = max(word_count / speech_rate, 1.0)

        # 휴지 1회당 평균 길이(초)는 config에서 주입
        estimated_pause_duration_sec = long_pause_count * _cfg("PAUSE_DURATION_SEC")

        # 총 추정 인터뷰 시간 = 발화 + 휴지
        total_estimated_duration = estimated_speech_duration_sec + estimated_pause_duration_sec
        pause_ratio = round(estimated_pause_duration_sec / total_estimated_duration, 4) if total_estimated_duration > 0 else 0.0

        # 휴지 빈도 정규화: 발화 100단어당 pause 횟수
        pause_frequency_per_100w = round((long_pause_count / word_count) * 100, 2) if word_count > 0 else 0.0

        # 휴지 패턴 심각도 분류 (경계값은 SPEECH_CONFIG에서 주입)
        _sev_th = _cfg("PAUSE_SEVERITY_THRESHOLDS")
        if long_pause_count == 0:
            pause_severity = "none"
        elif long_pause_count <= _sev_th["minimal"]:
            pause_severity = "minimal"
        elif long_pause_count <= _sev_th["moderate"]:
            pause_severity = "moderate"
        elif long_pause_count <= _sev_th["high"]:
            pause_severity = "high"
        else:
            pause_severity = "critical"

        # 필러워드 + 휴지 + 근접 반복 복합 지수 (높을수록 발화 흐름 불안정)
        # 반복은 필러(0.5)와 휴지(1.5) 사이의 중간 가중치(1.0)로 반영한다.
        dysfluency_composite_index = round(
            (total_filler * 0.5 + long_pause_count * 1.5 + repetition_count * 1.0) / max(word_count / 10, 1),
            3,
        )

        pause_analysis = {
            "long_pause_count": long_pause_count,
            "estimated_speech_duration_sec": round(estimated_speech_duration_sec, 1),
            "estimated_pause_duration_sec": round(estimated_pause_duration_sec, 1),
            "pause_ratio": pause_ratio,                         # 전체 시간 대비 휴지 비율
            "pause_frequency_per_100w": pause_frequency_per_100w,  # 100단어당 pause 횟수
            "pause_severity": pause_severity,                   # none/minimal/moderate/high/critical
            "dysfluency_composite_index": dysfluency_composite_index,  # 복합 비유창성 지수
        }
        # ────────────────────────────────────────────────────────────────

        duration = time.time() - start_time
        logger.info(
            "[Task A 완료] 필러워드: %d회, 중복 발화: %d건, pause 패턴: %s (%.3fs)",
            total_filler, len(repetition_scans), pause_severity, duration,
        )

        return {
            "filler_word_counts": filler_counts,
            "total_filler_count": total_filler,
            "long_pause_count": long_pause_count,
            "repetitions": repetition_scans,
            "repetition_count": repetition_count,
            "is_sentence_incomplete": False,
            "pause_analysis": pause_analysis,   # E7.6
        }

    # ── 파이프라인 내부 단계별 private 메서드 ────────────────────────────

    @staticmethod
    def _call_llm_chains(answer_text: str, question_type: str) -> tuple[dict, dict, dict]:
        """[Task B/C/D] 질문 유형에 따라 LLM 체인을 병렬 호출한다.

        Returns:
            (grounding_res, cbi_res, emotion_intent_res)
            기술 질문이 아닐 경우 grounding_res는 빈 fallback dict를 반환한다.
        """
        # 빈/초단문 답변: LLM 호출은 비용만 들고 결과가 무의미 → 조기 단락(0점 스텁 반환).
        if len(answer_text.strip()) < MIN_ANSWER_CHARS_FOR_LLM:
            logger.info(
                "답변이 너무 짧아 LLM 평가 생략 (chars=%d < %d)",
                len(answer_text.strip()), MIN_ANSWER_CHARS_FOR_LLM,
            )
            return _empty_llm_results()

        logger.info("📡 LLM 병렬 호출 시작 (question_type=%s)", question_type)
        if question_type == "technical":
            grounding_res, cbi_res, emotion_intent_res = eval_llm_chains_parallel_with_emotion(answer_text)
            logger.info("📡 LLM 응답 완료 (grounding / competency / emotion_intent)")
        else:
            # 비기술 질문은 grounding 지표가 의미 없으므로 해당 LLM 호출을 생략해 비용·지연을 줄인다.
            cbi_res, emotion_intent_res = eval_llm_chains_competency_emotion(answer_text)
            grounding_res = {
                "tech_stack": None,
                "before_metric": None,
                "after_metric": None,
                "is_grounded": False,
            }
            logger.info("📡 LLM 응답 완료 (competency / emotion_intent) — grounding 생략")
        return grounding_res, cbi_res, emotion_intent_res

    @staticmethod
    def _extract_qualitative_scores(cbi_res: dict) -> tuple[dict, dict, dict, dict, float, int, float]:
        """[정성 지표 정산] BEI STAR 4요소 및 CBI 점수를 cbi_res에서 추출한다.

        Returns:
            (situation, task, action, result, bei_total, cbi_level, cbi_mapped_score)
        """
        bei_star = cbi_res.get("bei_star", {})
        cbi_competency = cbi_res.get("cbi_competency", {})

        situation = bei_star.get("situation", {})
        task      = bei_star.get("task", {})
        action    = bei_star.get("action", {})
        result    = bei_star.get("result", {})

        # 수집 지점 클램핑(E 리뷰 #1): LLM이 정의 범위(0~25)를 벗어난 STAR 점수를 줘도 제한한다.
        # dict in-place로 되써, 저장되는 bei_score와 같은 객체를 읽는 tag_router(_route_tags)가
        # 모두 클램핑된 값을 보게 한다.
        for _label, _comp in (("situation", situation), ("task", task),
                              ("action", action), ("result", result)):
            if isinstance(_comp, dict):
                _clamped, _adjusted = _clamp_score(_comp.get("score", 0), 0, BEI_COMPONENT_SCORE_MAX)
                if _adjusted:
                    logger.warning(
                        "[클램핑] BEI %s score=%r → %s (유효범위 0~%d)",
                        _label, _comp.get("score", 0), _clamped, BEI_COMPONENT_SCORE_MAX,
                    )
                _comp["score"] = _clamped

        bei_total = (
            situation.get("score", 0)
            + task.get("score", 0)
            + action.get("score", 0)
            + result.get("score", 0)
        )
        cbi_level       = cbi_competency.get("assigned_level", 1)
        _raw_cbi_score   = cbi_competency.get("score", float(cbi_level * 20))
        cbi_mapped_score, _cbi_adjusted = _clamp_score(_raw_cbi_score, 0, CBI_SCORE_MAX)
        if _cbi_adjusted:
            logger.warning(
                "[클램핑] CBI score=%r → %s (유효범위 0~%d)",
                _raw_cbi_score, cbi_mapped_score, CBI_SCORE_MAX,
            )
        # tag_router가 cbi_competency["score"]를 직접 읽을 수 있으므로 되써준다.
        if isinstance(cbi_competency, dict):
            cbi_competency["score"] = cbi_mapped_score

        logger.info(
            "[정성 지표 정산] BEI 총합: %s점, CBI 레벨: %s (환산: %s점)",
            bei_total, cbi_level, cbi_mapped_score,
        )
        return situation, task, action, result, bei_total, cbi_level, cbi_mapped_score

    @staticmethod
    def _calculate_speech_score(dysfluency_res: dict) -> tuple[float, float, dict]:
        """[정량 지표 감점 산정] 필러워드·휴지 패턴 기반 Speech Score를 계산한다.

        Returns:
            (final_speech_score, pause_penalty, pause_analysis_data)
        """
        base_speech_score = _cfg("BASE_SCORE")
        penalty_per_count = _cfg("FILLER_PENALTY_PER_COUNT")
        floor_score       = _cfg("FLOOR_SCORE")

        total_fillers          = dysfluency_res.get("total_filler_count", 0)
        calculated_speech_score = base_speech_score - (total_fillers * penalty_per_count)

        # E7.6 — pause_ratio·severity 기반 추가 감점
        pause_analysis_data = dysfluency_res.get("pause_analysis", {})
        pause_ratio   = pause_analysis_data.get("pause_ratio", 0.0)
        pause_severity = pause_analysis_data.get("pause_severity", "none")
        pause_penalty  = _cfg("PAUSE_SEVERITY_PENALTY").get(pause_severity, 0.0)

        _ratio_threshold = _cfg("PAUSE_RATIO_THRESHOLD")
        if pause_ratio > _ratio_threshold:
            pause_penalty += (pause_ratio - _ratio_threshold) * _cfg("PAUSE_RATIO_PENALTY_SCALE")

        final_speech_score = max(calculated_speech_score - pause_penalty, floor_score)
        logger.info(
            "⚙️ [Speech Score] 필러감점=%.1f, 휴지감점=%.1f (severity=%s, ratio=%.2f) → %.1f",
            total_fillers * penalty_per_count, pause_penalty, pause_severity, pause_ratio, final_speech_score,
        )
        return final_speech_score, pause_penalty, pause_analysis_data

    @staticmethod
    def _calculate_overall_score(
        question_type: str,
        bei_total: float,
        cbi_mapped_score: float,
        final_speech_score: float,
        grounding_res: dict,
    ) -> float:
        """[최종 스코어링] 질문 유형별 가중치 공식으로 overall_score를 산출한다.

        기술 질문:  BEI×0.4 + CBI×0.4 + Speech×0.2 + grounding bonus(+15)
        인성/기타: BEI×0.5 + CBI×0.3 + Speech×0.2
        """
        if question_type == "technical":
            grounding_applicable = grounding_res.get("grounding_applicable", True)
            is_grounded_flag     = grounding_res.get("is_grounded", False)
            grounding_premium    = 15.0 if (grounding_applicable and is_grounded_flag) else 0.0
            raw_calc = (
                (bei_total * 0.4)
                + (cbi_mapped_score * 0.4)
                + (final_speech_score * 0.2)
                + grounding_premium
            )
            logger.info(
                "⚙️ [기술면접 스코어링] grounding_applicable=%s, is_grounded=%s → premium +%.1f",
                grounding_applicable, is_grounded_flag, grounding_premium,
            )
        else:
            raw_calc = (
                (bei_total * 0.5)
                + (cbi_mapped_score * 0.3)
                + (final_speech_score * 0.2)
            )
            logger.info(
                "[인성/기타면접 스코어링] BEI=%.1f×0.5 + CBI=%.1f×0.3 + Speech=%.1f×0.2 = %.1f",
                bei_total, cbi_mapped_score, final_speech_score, raw_calc,
            )
        return min(round(raw_calc, 1), 100.0)

    @staticmethod
    def _route_tags(
        question_type: str,
        bei_star: dict,
        cbi_res: dict,
        grounding_res: dict,
        dysfluency_res: dict,
        long_pause_count: int,
        word_count: int,
        overall_score: float,
        answer_text: str,
        llm_weakness_tags: list,
    ) -> dict:
        """[태그 라우팅] 디터미니스틱 강점/약점 태그를 산출한다.

        interview 팀 sufficiency 체인이 넘긴 llm_weakness_tags를 우선 사용하며,
        없을 경우 cbi_res의 llm_weakness_tags로 폴백한다.
        route_deterministic_tags가 내부에서 이미 병합하므로 여기서 중복 추가하지 않는다.
        """
        effective_llm_tags = llm_weakness_tags or cbi_res.get("llm_weakness_tags", []) or []
        deterministic_tags = route_deterministic_tags(
            question_type=question_type,
            bei_star=bei_star,
            cbi_res=cbi_res,
            grounding_res=grounding_res,
            total_filler=dysfluency_res.get("total_filler_count", 0),
            long_pause_count=long_pause_count,
            raw_word_count=word_count,
            tech_score=overall_score,
            stt_text=answer_text,
            llm_weakness_tags=effective_llm_tags,
        )
        return {
            "strengths": deterministic_tags.get("strengths", []),
            "weaknesses": deterministic_tags.get("weaknesses", []),
        }

    # ── 공개 파이프라인 진입점 ────────────────────────────────────────────

    @staticmethod
    def run_pipeline(
        answer_text: str,
        question_type: str = "technical",
        long_pause_count: int = 0,
        llm_weakness_tags: list = None,
    ) -> dict:
        """면접 답변 하나에 대한 전체 평가 파이프라인을 실행한다.

        Steps:
            A. 로컬 비유창성 분석 (필러워드·휴지)
            B/C/D. LLM 체인 병렬 호출 (grounding / competency / emotion_intent)
            E. 정성 지표 정산 (BEI STAR, CBI)
            F. Speech Score 감점 산정
            G. Overall Score 통합
            H. 강점/약점 태그 라우팅
        """
        pipeline_start_time = time.time()
        logger.info("🚀 EVALUATION PIPELINE START (question_type=%s)", question_type)

        # A. 인풋 검증 + 로컬 비유창성 분석
        word_count = len(answer_text.split())
        logger.info("[인풋] 글자 수: %d자, 단어 수: %d개", len(answer_text), word_count)
        dysfluency_res = EvaluationService.analyze_dysfluency_local(answer_text, long_pause_count)

        # B/C/D. LLM 병렬 호출
        grounding_res, cbi_res, emotion_intent_res = EvaluationService._call_llm_chains(
            answer_text, question_type
        )

        # E. 정성 지표 정산
        situation, task, action, result, bei_total, cbi_level, cbi_mapped_score = (
            EvaluationService._extract_qualitative_scores(cbi_res)
        )

        # F. Speech Score 감점 산정
        final_speech_score, pause_penalty, pause_analysis_data = (
            EvaluationService._calculate_speech_score(dysfluency_res)
        )

        # G. Overall Score 통합
        overall_score = EvaluationService._calculate_overall_score(
            question_type, bei_total, cbi_mapped_score, final_speech_score, grounding_res
        )

        pipeline_elapsed = round(time.time() - pipeline_start_time, 3)
        logger.info("✅ PIPELINE DONE (%.3fs) overall_score=%.1f", pipeline_elapsed, overall_score)

        # H. 강점/약점 태그 라우팅
        pipeline_tags = EvaluationService._route_tags(
            question_type=question_type,
            bei_star=cbi_res.get("bei_star", {}),
            cbi_res=cbi_res,
            grounding_res=grounding_res,
            dysfluency_res=dysfluency_res,
            long_pause_count=long_pause_count,
            word_count=word_count,
            overall_score=overall_score,
            answer_text=answer_text,
            llm_weakness_tags=llm_weakness_tags or [],
        )

        total_fillers     = dysfluency_res.get("total_filler_count", 0)
        penalty_per_count = _cfg("FILLER_PENALTY_PER_COUNT")
        cbi_competency    = cbi_res.get("cbi_competency", {})

        return {
            "bei_score": {
                "situation": situation,
                "task": task,
                "action": action,
                "result": result,
            },
            "cbi_score": {
                "assigned_level": cbi_level,
                "score": cbi_mapped_score,
                "evidence_sentence": cbi_competency.get("evidence_sentence", ""),
            },
            "filler_words": {
                "counts": dysfluency_res.get("filler_word_counts", {}),
                "total": total_fillers,
                "repetitions": dysfluency_res.get("repetitions", []),
                "repetition_count": dysfluency_res.get("repetition_count", 0),
            },
            "answer_score": int(overall_score),
            "score_detail": {
                "grounding": grounding_res,
                "speech_delivery": {
                    "speech_score": final_speech_score,
                    "filler_penalty": total_fillers * penalty_per_count,
                    "pause_penalty": pause_penalty,
                },
                "pause_analysis": pause_analysis_data,
                "pipeline_elapsed_sec": pipeline_elapsed,
            },
            "emotion_intent_score": emotion_intent_res,
            "pipeline_tags": pipeline_tags,
        }
