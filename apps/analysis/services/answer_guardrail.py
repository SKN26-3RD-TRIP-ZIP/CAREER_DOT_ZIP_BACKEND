"""
STAR 답변 groundedness 가드레일 (결정적, LLM 미사용)

목적:
  LLM이 사용자가 말한 적 없는 정량 성과를 지어내는 것(할루시네이션)을 차단한다.
  예: 이력서엔 없는데 답변이 "응답속도를 40% 개선" → 사용자가 면접에서 거짓말을
      하게 되는, 가장 해로운 품질 결함.

전략:
  답변에 등장하는 "정량 수치(단위가 붙은 숫자)"가 원본 자료(이력서·자소서·JD)에
  실제로 존재하는지 검증한다. 없으면 unsupported로 표시한다.
  - 단위 없는 맨 숫자(예: '3명이서'의 3)는 위험도가 낮아 제외하고,
    성과/지표성 수치(%, 배, 건, 개, 명, 만, 천 ...)에 집중한다.

사용:
  star_service.generate_star_answers()가 각 답변에 groundedness 메타를 붙이고,
  프론트는 unsupported가 있으면 "이력서에서 확인되지 않은 수치" 경고를 노출한다.
"""

import re

# 지표성 단위 (이 단위가 붙은 숫자만 "성과 주장"으로 간주)
_UNIT = r"%|퍼센트|배|건|개|명|위|개월|년|주|시간|만|천|억|원|달러|점|위"
_METRIC_RE = re.compile(rf"(\d[\d,]*\.?\d*)\s*({_UNIT})")

# 표기 정규화 (동일 수치의 다른 표기를 같은 키로)
_UNIT_ALIAS = {"퍼센트": "%"}


def _metrics(text: str) -> set[str]:
    """텍스트에서 단위 붙은 정량 토큰을 추출해 '숫자+단위' 집합으로 반환."""
    found = set()
    for num, unit in _METRIC_RE.findall(text or ""):
        num = num.replace(",", "")
        unit = _UNIT_ALIAS.get(unit, unit)
        found.add(f"{num}{unit}")
    return found


def check_groundedness(answer_text: str, source_text: str) -> dict:
    """
    답변의 정량 수치가 원본 자료에 근거하는지 검증한다.

    Returns:
        {
            "grounded":    bool,        # 지어낸 수치가 없으면 True
            "unsupported": ["40%", ...],# 원본에서 못 찾은 수치 (지어냈을 가능성)
        }
    """
    answer_metrics = _metrics(answer_text)
    source_metrics = _metrics(source_text)
    unsupported = sorted(answer_metrics - source_metrics)
    return {"grounded": not unsupported, "unsupported": unsupported}


def check_answer(answer: dict, source_text: str) -> dict:
    """
    STAR 답변 dict 전체(summary~result)를 합쳐 groundedness를 검사한다.
    STAR 필드 중 정량 주장이 가장 많은 곳은 result라 가중치 없이 합쳐도 충분하다.
    """
    joined = " ".join(
        str(answer.get(k, ""))
        for k in ("summary", "situation", "task", "action", "result")
    )
    return check_groundedness(joined, source_text)
