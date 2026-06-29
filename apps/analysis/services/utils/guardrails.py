"""
입출력 가드레일

InputGuardrail  — 분석 API 입력값(JD·자소서)의 유효성을 규칙 기반 1차 검사와
                  LLM 기반 2차 검사로 순서대로 검증한다.
OutputGuardrail — LLM이 생성한 질문 목록을 후처리(길이 필터 + 중복 제거)한다.
"""

import logging
from ..analysis_prompt import build_guardrail_jd_check_user, build_guardrail_cl_check_user

logger = logging.getLogger(__name__)

# ── 길이 제한 상수 ─────────────────────────────────────────────────
_JD_MIN_LEN           = 20
_JD_MAX_LEN           = 10_000
_COVER_LETTER_MIN_LEN = 10
_COVER_LETTER_MAX_LEN = 5_000

_INJECTION_PATTERNS: list[str] = [
    "이전 지시를 무시",
    "ignore previous",
    "당신은 이제",
    "forget your instructions",
    "new instruction",
    "system prompt",
]

# TODO: 욕설 금지어 목록 추가 (현재 비어 있음)
_BANNED_WORDS: list[str] = []


class InputGuardrail:
    """
    입력값에 대해 규칙 기반 1차 검사와 LLM 기반 2차 검사를 수행한다.

    검사 순서:
      1차 — 길이 범위·프롬프트 인젝션·금지어 (LLM 호출 없음, 빠르고 무료)
      2차 — LLM 분류 (1차 전부 통과한 경우에만 실행)

    LLM 호출 실패 시 2차 검사를 스킵하고 통과 처리한다 (가드레일 오류가 서비스를 막으면 안 됨).

    길이 제한은 생성자 인자로 재정의할 수 있다.
    """

    def __init__(
        self,
        jd_min_len:           int = _JD_MIN_LEN,
        jd_max_len:           int = _JD_MAX_LEN,
        cover_letter_min_len: int = _COVER_LETTER_MIN_LEN,
        cover_letter_max_len: int = _COVER_LETTER_MAX_LEN,
    ) -> None:
        """
        Args:
            jd_min_len:           JD 최소 글자 수 (기본 20)
            jd_max_len:           JD 최대 글자 수 (기본 10,000)
            cover_letter_min_len: 자소서 최소 글자 수 (기본 10)
            cover_letter_max_len: 자소서 최대 글자 수 (기본 5,000)
        """
        self.jd_min_len           = jd_min_len
        self.jd_max_len           = jd_max_len
        self.cover_letter_min_len = cover_letter_min_len
        self.cover_letter_max_len = cover_letter_max_len

    def validate(self, jd: str = None, cover_letter: str = None) -> dict:
        """
        jd와 cover_letter를 순서대로 검사한다.
        1차 규칙 기반 → 통과 시 2차 LLM 분류 순서를 반드시 지킨다.

        Args:
            jd:           채용공고(JD) 원문 텍스트 (None 허용 — 검사 스킵)
            cover_letter: 자기소개서 텍스트 (None 또는 빈 문자열 허용 — 검사 스킵)

        Returns:
            통과: {"valid": True}
            실패: {"valid": False, "field": "필드명", "error": "사용자에게 노출할 메시지"}
        """
        # ── 1차: 규칙 기반 검사 (LLM 호출 없음) ──────────────────────

        # JD 길이 검사
        if jd is not None:
            if len(jd) < self.jd_min_len:
                return {
                    "valid": False,
                    "field": "jd",
                    "error": "채용공고 내용이 너무 짧습니다. 20자 이상 입력해주세요.",
                }
            if len(jd) > self.jd_max_len:
                return {
                    "valid": False,
                    "field": "jd",
                    "error": "채용공고 내용이 너무 깁니다.",
                }

        # 자소서 길이 검사
        if cover_letter:
            if len(cover_letter) < self.cover_letter_min_len:
                return {
                    "valid": False,
                    "field": "cover_letter",
                    "error": "자소서 내용이 너무 짧습니다. 10자 이상 입력해주세요.",
                }
            if len(cover_letter) > self.cover_letter_max_len:
                return {
                    "valid": False,
                    "field": "cover_letter",
                    "error": "자소서 내용이 너무 깁니다.",
                }

        # 프롬프트 인젝션 패턴 검사 (jd, cover_letter 각각)
        for field_name, text in [("jd", jd or ""), ("cover_letter", cover_letter or "")]:
            text_lower = text.lower()
            for pattern in _INJECTION_PATTERNS:
                if pattern.lower() in text_lower:
                    logger.warning("[InputGuardrail] 프롬프트 인젝션 패턴 탐지: '%s' in %s", pattern, field_name)
                    return {
                        "valid": False,
                        "field": field_name,
                        "error": "올바른 형식으로 입력해주세요.",
                    }

        # 욕설 금지어 검사
        combined = f"{jd or ''} {cover_letter or ''}".lower()
        for word in _BANNED_WORDS:
            if word.lower() in combined:
                logger.warning("[InputGuardrail] 금지어 탐지: '%s'", word)
                return {
                    "valid": False,
                    "field": "jd",
                    "error": "입력에 부적절한 표현이 포함되어 있습니다. 내용을 확인 후 다시 시도해주세요.",
                }

        # ── 2차: LLM 분류 (1차 전부 통과 후에만 실행) ─────────────────
        # 너무 엄격하게 막아서 제외.
        # try:
        #     llm_result = self._llm_validate(jd=jd, cover_letter=cover_letter)
        #     if llm_result and not llm_result["valid"]:
        #         return llm_result
        # except Exception as e:
        #     # LLM 호출 실패 시 서비스를 막지 않고 통과 처리
        #     logger.warning("[InputGuardrail] LLM 2차 검사 실패 — 스킵하고 통과 처리: %s", e)

        return {"valid": True}

    def _llm_validate(self, jd: str = None, cover_letter: str = None) -> dict | None:
        """
        LLM을 이용해 입력 내용이 올바른 종류인지 분류한다.
        통과 시 None, 실패 시 {"valid": False, ...} 반환.
        예외는 호출자(validate)에서 잡는다.
        """
        from .llm_helpers import get_client
        client = get_client()

        # JD 분류
        if jd:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[{"role": "user", "content": build_guardrail_jd_check_user(jd)}],
            )
            answer = response.choices[0].message.content.strip().upper()
            if answer.startswith("NO"):
                return {
                    "valid": False,
                    "field": "jd",
                    "error": "채용공고와 관련된 내용을 입력해주세요.",
                }

        # 자소서 분류
        if cover_letter:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[{"role": "user", "content": build_guardrail_cl_check_user(cover_letter)}],
            )
            answer = response.choices[0].message.content.strip().upper()
            if answer.startswith("NO"):
                return {
                    "valid": False,
                    "field": "cover_letter",
                    "error": "이력서 또는 자소서 내용을 입력해주세요.",
                }

        return None


class OutputGuardrail:
    """
    LLM이 생성한 질문 리스트를 검사하고 필터링한다.

    - 10자 미만 질문 제거
    - existing_questions와 완전히 동일한 텍스트 제거 (strip 후 비교)
    - 필터 후 빈 리스트여도 예외 발생 금지
    """

    def filter(self, questions: list, existing_questions: list = None) -> list:
        """
        생성된 질문 리스트에서 품질 미달 및 중복 질문을 제거한다.

        Args:
            questions:          LLM이 생성한 질문 dict 목록.
                                각 항목은 "question_text" 또는 "text" 키를 포함해야 한다.
            existing_questions: 동일 세션에 이미 저장된 question_text 문자열 목록.
                                None이면 빈 리스트로 처리한다.

        Returns:
            필터링된 질문 dict 목록 (빈 리스트 포함 가능)
        """
        existing_set = {q.strip() for q in (existing_questions or [])}
        filtered = []

        for q in questions:
            text = (q.get("question_text") or q.get("text", "")).strip()

            if len(text) < 10:
                logger.debug("[OutputGuardrail] 짧은 질문 제거: '%s'", text)
                continue

            if text in existing_set:
                logger.debug("[OutputGuardrail] 중복 질문 제거: '%s'", text)
                continue

            filtered.append(q)

        return filtered
