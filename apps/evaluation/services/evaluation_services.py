import re
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

# 💡 settings.py에 선언한 SPEECH_CONFIG를 안전하게 맵핑 (없을 경우를 대비한 Fallback 방어코드 포함)
SPEECH_CONFIG = getattr(settings, "SPEECH_CONFIG", {
    "BASE_SCORE": 80.0,   # settings.SPEECH_CONFIG와 일치 (완벽한 전달력도 80 상한)
    "FILLER_PENALTY_PER_COUNT": 5.0,
    "FLOOR_SCORE": 20.0,
    "EXCESSIVE_FILLER_LIMIT": 6,
})

# 💡 E7.6 휴지 파라미터 — settings.SPEECH_CONFIG에 키가 없을 때의 방어 기본값
_PAUSE_DEFAULTS = {
    "SPEECH_RATE_WORDS_PER_SEC": 3.0,
    "PAUSE_DURATION_SEC": 3.0,
    "PAUSE_RATIO_THRESHOLD": 0.30,
    "PAUSE_RATIO_PENALTY_SCALE": 50.0,
    "PAUSE_SEVERITY_PENALTY": {
        "none": 0.0, "minimal": 0.0, "moderate": 5.0, "high": 12.0, "critical": 22.0,
    },
    "PAUSE_SEVERITY_THRESHOLDS": {"minimal": 1, "moderate": 3, "high": 6},
}


def _cfg(key):
    """SPEECH_CONFIG에서 값을 읽되, 누락 시 E7.6 기본값으로 폴백."""
    return SPEECH_CONFIG[key] if key in SPEECH_CONFIG else _PAUSE_DEFAULTS[key]

# 로거 정의
logger = logging.getLogger("feedback_ai.evaluation_service")

kiwi = Kiwi()
FILLER_WORDS = ["어", "음", "그니까", "그러니까", "사실", "이제", "저기"]


class EvaluationService:

    @staticmethod
    def analyze_dysfluency_local(stt_text: str, long_pause_count: int = 0) -> dict:
        """[Task A] 로컬 비유창성 분석 (원본 알고리즘 보존 + E7.6 휴지 패턴 고도화)"""
        logger.info("=== [Task A] 로컬 비유창성 분석 시작 ===")
        start_time = time.time()

        # 형태소 토큰을 먼저 산출 — 단음절 필러의 부분문자열 오탐(예: "들어","어렵다",
        # "마음","처음")을 막기 위해 토큰 경계 기준으로 카운트한다.
        tokens = [t.form for t in kiwi.tokenize(stt_text)]
        token_counter = Counter(tokens)

        filler_counts = {}
        total_filler = 0
        for word in FILLER_WORDS:
            if len(word) == 1:
                # 단음절 필러("어","음")는 형태소 토큰 정확 일치로만 카운트
                count = token_counter.get(word, 0)
            else:
                # 다음절 필러는 부분문자열 + 말줄임("그러니까...") 패턴 중 큰 값
                plain_count = stt_text.count(word)
                ellipsis_count = len(re.findall(rf'{re.escape(word)}\.+', stt_text))
                count = max(plain_count, ellipsis_count)
            if count > 0:
                filler_counts[word] = count
                total_filler += count

        repetition_scans = []
        for i in range(len(tokens) - 1):
            if tokens[i] == tokens[i+1] and len(tokens[i]) > 1:
                repetition_scans.append(tokens[i])

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

        # 필러워드 + 휴지 복합 지수 (높을수록 발화 흐름 불안정)
        dysfluency_composite_index = round(
            (total_filler * 0.5 + long_pause_count * 1.5) / max(word_count / 10, 1),
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

        bei_total = (
            situation.get("score", 0)
            + task.get("score", 0)
            + action.get("score", 0)
            + result.get("score", 0)
        )
        cbi_level       = cbi_competency.get("assigned_level", 1)
        cbi_mapped_score = cbi_competency.get("score", float(cbi_level * 20))

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
        base_speech_score = SPEECH_CONFIG.get("BASE_SCORE", 100.0)
        penalty_per_count = SPEECH_CONFIG.get("FILLER_PENALTY_PER_COUNT", 5.0)
        floor_score       = SPEECH_CONFIG.get("FLOOR_SCORE", 20.0)

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
        penalty_per_count = SPEECH_CONFIG.get("FILLER_PENALTY_PER_COUNT", 5.0)
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
            },
            "final_tech_score": int(overall_score),
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
