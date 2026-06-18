"""질문별 개선 액션 문구 LLM 생성 서비스 (리포트 전용).

기존에는 question_breakdown의 improvement_action이 weakness 태그의
고정 description(예: "주장에 대한 근거, 사례, 수치, 결과가 부족하여 객관성이 떨어짐")을
그대로 노출해, 같은 약점 태그가 붙은 질문들이 모두 동일한 문구로 표시됐다.

이 서비스는 (질문 + 답변 + 감지된 약점 + 점수)를 LLM에 한 번에 배치로 넘겨
질문별로 구체적이고 실행 가능한 개선 제안을 생성한다.

설계 원칙
  - 리포트당 LLM 호출 1회(질문 배치) — 답변 수만큼 호출하지 않는다.
  - 실패/모의(mock) 환경에서는 예외를 던지지 않고 빈 dict를 반환한다.
    호출부(report_generator)가 기존 템플릿 문구로 폴백한다.
  - 평가 점수 산출 로직과 완전히 분리 — 점수에 영향 없음.
"""

import json
import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger("feedback_ai.improvement_suggester")

# evaluation_chains와 동일 컨벤션: 키/모델/모의 플래그 재사용
_OPENAI_KEY = getattr(settings, "OPENAI_API_KEY", None)
_MODEL = getattr(settings, "IMPROVEMENT_SUGGESTER_MODEL", "gpt-4o-mini")
_ANSWER_EXCERPT_LIMIT = 700  # 토큰 제어용 답변 발췌 길이

_SYSTEM_PROMPT = (
    "당신은 10년 차 시니어 면접 코치입니다. 지원자의 '질문/답변/감지된 약점/점수'를 보고, "
    "질문마다 한국어 존댓말로 1~2문장의 '구체적이고 실행 가능한' 개선 제안을 작성합니다.\n"
    "규칙:\n"
    "1. 반드시 해당 답변의 실제 내용에 근거해 작성하고, 일반론(예: '근거가 부족합니다')만 반복하지 마세요.\n"
    "2. 무엇을(what) 어떻게(how) 보완할지 행동 단위로 제시하세요. 가능하면 답변에서 빠진 수치/사례/구조를 짚어주세요.\n"
    "3. 비난조가 아니라 코칭 톤으로, 한 문장은 간결하게.\n"
    "4. 출력은 반드시 JSON. 형식: {\"suggestions\": [{\"question_id\": \"<id>\", \"improvement\": \"<문구>\"}]}\n"
    "5. 입력으로 받은 question_id를 그대로 사용하고, 모든 질문에 대해 항목을 빠짐없이 반환하세요."
)


def _use_mock() -> bool:
    return getattr(settings, "OPENAI_USE_MOCK", False)


def _build_user_payload(items: list[dict]) -> str:
    """LLM 입력용 질문 배열을 JSON 문자열로 직렬화한다."""
    compact = []
    for it in items:
        answer = (it.get("answer_text") or "").strip()
        if len(answer) > _ANSWER_EXCERPT_LIMIT:
            answer = answer[:_ANSWER_EXCERPT_LIMIT] + "…"
        compact.append({
            "question_id": it["question_id"],
            "question": it.get("question_text", ""),
            "answer": answer or "(답변 없음)",
            "weaknesses": it.get("weaknesses", []),
            "score": it.get("score", 0),
            "grounding_gaps": it.get("grounding_gaps", []),
        })
    return json.dumps({"questions": compact}, ensure_ascii=False)


def generate_improvement_suggestions(items: list[dict]) -> dict[str, str]:
    """질문별 개선 문구를 생성한다.

    Args:
        items: [{question_id, question_text, answer_text, weaknesses[list[str]],
                 grounding_gaps[list[str]], score}] 목록.

    Returns:
        {question_id: improvement_text} 매핑. 모의/실패 시 빈 dict.
        (호출부는 빈 값에 대해 기존 템플릿 문구로 폴백한다.)
    """
    if not items:
        return {}

    if _use_mock() or not _OPENAI_KEY:
        logger.info("improvement_suggester: mock/no-key 모드 — 템플릿 폴백 사용")
        return {}

    try:
        client = OpenAI(api_key=_OPENAI_KEY)
        res = client.chat.completions.create(
            model=_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_payload(items)},
            ],
            timeout=20.0,
        )
        raw = json.loads(res.choices[0].message.content)
        suggestions = raw.get("suggestions", [])
        result: dict[str, str] = {}
        for s in suggestions:
            qid = s.get("question_id")
            text = (s.get("improvement") or "").strip()
            if qid and text:
                result[str(qid)] = text
        logger.info(
            "improvement_suggester: %d/%d 질문 개선 문구 생성", len(result), len(items)
        )
        return result
    except Exception:
        logger.exception("improvement_suggester 실패 — 템플릿 폴백")
        return {}
