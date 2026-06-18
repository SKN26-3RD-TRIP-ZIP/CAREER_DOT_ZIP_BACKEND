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

openai_key = getattr(settings, "OPENAI_API_KEY", None)
client = OpenAI(api_key=openai_key)

# OPENAI_USE_MOCK=True → 실패 시 mock fallback 허용 (개발/테스트용)
# OPENAI_USE_MOCK=False(기본) → real mode: 실패 시 예외 전파, 0점 silent fallback 금지
USE_MOCK = getattr(settings, "OPENAI_USE_MOCK", False)


def _use_mock() -> bool:
    return getattr(settings, "OPENAI_USE_MOCK", False)


def fetch_grounding(answer_text: str) -> dict:
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EVAL_GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": answer_text}
            ],
            timeout=15.0,
        )
        return json.loads(res.choices[0].message.content)
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
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": answer_text}
            ],
            timeout=15.0,
        )
        return json.loads(res.choices[0].message.content)

    except Exception as e:
        logger.error(f"OpenAI fetch_competency failed: {str(e)}", exc_info=True)
        if not _use_mock():
            # real mode: 예외를 그대로 전파 → session_evaluation이 per-answer 격리 처리
            raise
        # mock mode에서만 fallback 허용
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
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": answer_text},
            ],
            timeout=15.0,
        )
        raw = json.loads(res.choices[0].message.content)

        # 신뢰도 보정: 0.05 미만 레이블 제거 후 재정규화
        for label_key in ("emotion_labels", "competency_intent_labels"):
            labels = raw.get(label_key, {})
            if not isinstance(labels, dict):
                continue
            cleaned = {k: v for k, v in labels.items() if isinstance(v, (int, float)) and v >= 0.05}
            total = sum(cleaned.values())
            if total > 0:
                raw[label_key] = {k: round(v / total, 4) for k, v in cleaned.items()}
            else:
                raw[label_key] = labels

        return raw

    except Exception as e:
        logger.error(f"OpenAI fetch_emotion_intent failed: {str(e)}", exc_info=True)
        if not _use_mock():
            raise
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
