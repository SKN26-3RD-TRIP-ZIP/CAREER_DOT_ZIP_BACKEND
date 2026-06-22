# apps/evaluation/evaluation_chains.py
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from openai import OpenAI
from .evaluation_prompts import (
    EVAL_GROUNDING_SYSTEM_PROMPT,
    EVAL_COMPETENCY_SYSTEM_PROMPT,
    EVAL_COMPETENCY_FORMAT_PROMPT,
    EVAL_EMOTION_INTENT_SYSTEM_PROMPT,
    EVAL_EMOTION_INTENT_FORMAT_PROMPT,
)

logger = logging.getLogger("feedback_ai.evaluation_chains")


class EvaluationFormatError(Exception):
    """LLM 응답을 정해진 JSON 포맷으로 파싱하지 못함 (재시도 소진 후 발생).

    네트워크/인증 같은 일시 장애와 구분하기 위한 전용 예외다. 이 예외가 위로
    전파되면 리포트 생성 레이어가 사용자에게 에러 창을 띄우고 에러 로그를 남긴다.
    """


# OpenAI 클라이언트는 모듈 import 시점이 아니라 최초 호출 시 lazy 생성한다.
# (키가 없을 때 import만으로 죽지 않도록 — mock 모드 테스트/CI 보호)
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))
    return _client


def _use_mock() -> bool:
    """Read mock mode at call time so override_settings works in tests."""
    return getattr(settings, "OPENAI_USE_MOCK", False)


# 포맷 오류 시 LLM 재호출 횟수 (settings로 조정 가능). 최초 1회 + 재시도 N회.
_MAX_LLM_FORMAT_RETRIES = getattr(settings, "EVAL_LLM_MAX_RETRIES", 2)


def _chat_json(system_content: str, user_content: str, *, label: str, required_keys=None) -> dict:
    """OpenAI에 JSON 응답을 요청하고 파싱한다.

    응답 포맷이 깨지면(JSON 파싱 실패 또는 required_keys 누락) 같은 답변으로
    최대 _MAX_LLM_FORMAT_RETRIES회 재호출해 다시 채점한다. 모두 실패하면
    EvaluationFormatError를 던진다. 네트워크/인증 등 그 외 예외는 재시도 없이 전파한다.
    """
    last_err = None
    for attempt in range(1, _MAX_LLM_FORMAT_RETRIES + 2):
        res = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            timeout=15.0,
        )
        content = res.choices[0].message.content
        try:
            parsed = json.loads(content)
            if required_keys:
                missing = [k for k in required_keys if k not in parsed]
                if missing:
                    raise ValueError(f"필수 키 누락: {missing}")
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            logger.warning(
                "%s 응답 포맷 오류 — 재채점 재시도 (attempt=%d/%d): %s",
                label, attempt, _MAX_LLM_FORMAT_RETRIES + 1, e,
            )
            continue
        if attempt > 1:
            logger.info("%s 포맷 재시도 성공 (attempt=%d)", label, attempt)
        return parsed

    logger.error(
        "%s 응답 포맷 재시도 소진 (%d회) — EvaluationFormatError 발생",
        label, _MAX_LLM_FORMAT_RETRIES + 1,
    )
    raise EvaluationFormatError(f"{label}: {last_err}")


def fetch_grounding(answer_text: str) -> dict:
    try:
        return _chat_json(
            EVAL_GROUNDING_SYSTEM_PROMPT,
            answer_text,
            label="fetch_grounding",
            required_keys=("is_grounded",),
        )
    except EvaluationFormatError:
        # 포맷 재시도까지 소진 — mock이 아니면 위로 전파해 에러 창/로그를 띄운다.
        if not _use_mock():
            raise
        return {
            "tech_stack": "확인 불가",
            "before_metric": "확인 불가",
            "after_metric": "확인 불가",
            "is_grounded": False,
        }
    except Exception as e:
        logger.error(f"OpenAI fetch_grounding failed: {str(e)}", exc_info=True)
        if not _use_mock():
            # real mode: 예외를 그대로 전파 → session_evaluation이 per-answer 격리 처리
            raise
        # mock mode에서만 fallback 허용
        return {
            "tech_stack": "확인 불가",
            "before_metric": "확인 불가",
            "after_metric": "확인 불가",
            "is_grounded": False,
        }


def fetch_competency(answer_text: str) -> dict:
    full_system = f"{EVAL_COMPETENCY_SYSTEM_PROMPT}\n\n{EVAL_COMPETENCY_FORMAT_PROMPT}"

    try:
        return _chat_json(
            full_system,
            answer_text,
            label="fetch_competency",
            required_keys=("bei_star", "cbi_competency"),
        )
    except EvaluationFormatError:
        if not _use_mock():
            raise
        return _competency_fallback()
    except Exception as e:
        logger.error(f"OpenAI fetch_competency failed: {str(e)}", exc_info=True)
        if not _use_mock():
            # real mode: 예외를 그대로 전파 → session_evaluation이 per-answer 격리 처리
            raise
        # mock mode에서만 fallback 허용
        return _competency_fallback()


def _competency_fallback() -> dict:
    return {
        "bei_star": {
            "situation": {
                "desc": "OpenAI 연결 실패로 상황 평가를 진행하지 못했습니다.",
                "score": 0,
            },
            "task": {
                "desc": "OpenAI 연결 실패로 과제 평가를 진행하지 못했습니다.",
                "score": 0,
            },
            "action": {
                "desc": "OpenAI 연결 실패로 행동 평가를 진행하지 못했습니다.",
                "score": 0,
            },
            "result": {
                "desc": "OpenAI 연결 실패로 결과 평가를 진행하지 못했습니다.",
                "score": 0,
            },
        },
        "cbi_competency": {
            "assigned_level": 0,
            "score": 0,
            "evidence_sentence": "OpenAI 연결 실패로 역량 평가를 진행하지 못했습니다.",
        },
        "llm_weakness_tags": [],
    }


def fetch_emotion_intent(answer_text: str) -> dict:
    """E7.4 — 감정/의도 분류 엔진. 확률값 softmax 정규화 및 신뢰도 보정 포함."""
    full_system = f"{EVAL_EMOTION_INTENT_SYSTEM_PROMPT}\n\n{EVAL_EMOTION_INTENT_FORMAT_PROMPT}"
    try:
        raw = _chat_json(
            full_system,
            answer_text,
            label="fetch_emotion_intent",
            required_keys=("emotion_labels", "competency_intent_labels"),
        )

        # 신뢰도 보정: 0.05 미만 레이블 제거 후 재정규화하고, dominant 레이블도 재계산.
        for label_key in ("emotion_labels", "competency_intent_labels"):
            labels = raw.get(label_key, {})
            if not isinstance(labels, dict):
                continue
            cleaned = {k: v for k, v in labels.items() if isinstance(v, (int, float)) and v >= 0.05}
            total = sum(cleaned.values())
            if total > 0:
                normalized = {k: round(v / total, 4) for k, v in cleaned.items()}
                raw[label_key] = normalized
                # 재정규화로 순위가 바뀔 수 있으므로 dominant를 분포에서 직접 다시 뽑는다.
                dom_key = "dominant_emotion" if label_key == "emotion_labels" else "dominant_competency"
                raw[dom_key] = max(normalized, key=normalized.get)
            else:
                raw[label_key] = labels

        return raw

    except EvaluationFormatError:
        if not _use_mock():
            raise
        return _emotion_intent_fallback()
    except Exception as e:
        logger.error(f"OpenAI fetch_emotion_intent failed: {str(e)}", exc_info=True)
        if not _use_mock():
            raise
        return _emotion_intent_fallback()


def _emotion_intent_fallback() -> dict:
    return {
        "emotion_labels": {"neutral": 1.0},
        "competency_intent_labels": {"problem_solving": 1.0},
        "dominant_emotion": "neutral",
        "dominant_competency": "problem_solving",
        "confidence_score": 0.0,
        "evidence_note": "OpenAI 연결 실패로 감정/의도 분류를 수행하지 못했습니다.",
    }


def eval_grounding_chain(answer_text: str) -> dict:
    return fetch_grounding(answer_text)


def eval_competency_chain(answer_text: str) -> dict:
    return fetch_competency(answer_text)


def eval_emotion_intent_chain(answer_text: str) -> dict:
    return fetch_emotion_intent(answer_text)


def eval_llm_chains_parallel(answer_text: str) -> tuple[dict, dict]:
    """Run grounding and competency LLM calls concurrently."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        grounding_future = executor.submit(fetch_grounding, answer_text)
        competency_future = executor.submit(fetch_competency, answer_text)
        return grounding_future.result(), competency_future.result()


def eval_llm_chains_parallel_with_emotion(answer_text: str) -> tuple[dict, dict, dict]:
    """E7.4 포함 3-chain 병렬 실행 (grounding / competency / emotion_intent)."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        grounding_future = executor.submit(fetch_grounding, answer_text)
        competency_future = executor.submit(fetch_competency, answer_text)
        emotion_future = executor.submit(fetch_emotion_intent, answer_text)
        return grounding_future.result(), competency_future.result(), emotion_future.result()


def eval_llm_chains_competency_emotion(answer_text: str) -> tuple[dict, dict]:
    """grounding 체인 없이 competency + emotion_intent 만 병렬 실행.

    비기술(personality/general) 질문은 grounding 지표가 의미 없으므로
    해당 LLM 호출을 생략해 비용·지연을 줄인다.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        competency_future = executor.submit(fetch_competency, answer_text)
        emotion_future = executor.submit(fetch_emotion_intent, answer_text)
        return competency_future.result(), emotion_future.result()
