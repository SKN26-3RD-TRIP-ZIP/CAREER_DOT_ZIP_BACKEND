"""
Pipeline 1 - ④ 결과 출력

역할:
  match_service의 점수 산출 결과를 최종 응답 형태로 포맷팅한다.
  CI(합격 가능성 구간) 계산 및 최종 응답 조립을 담당한다.

포함 함수:
  build_match_result()       점수 + LLM 결과를 최종 응답 형태로 조립
  calc_confidence_interval() 합격 가능성 구간 산출
"""


def calc_confidence_interval(
    match_score: float,
    tech_score: float,
    trait_score: float,
    rule_score: float,
) -> dict:
    """
    매칭 점수를 바탕으로 합격 가능성 구간(CI)을 산출한다.

    구간 기준:
      match_score < 40  → "낮음"        (±5)
      40 <= score < 60  → "가능성 있음"  (-8 / +8)
      60 <= score < 80  → "높음"         (-5 / +10)
      score >= 80       → "매우 높음"    (-3 / +5)

    rule_score == 0이면 CI 범위를 ±5 추가로 확장 (불확실성 반영).
    """
    if match_score < 40:
        label = "낮음"
        low, high = match_score - 5, match_score + 5
    elif match_score < 60:
        label = "가능성 있음"
        low, high = match_score - 8, match_score + 8
    elif match_score < 80:
        label = "높음"
        low, high = match_score - 5, match_score + 10
    else:
        label = "매우 높음"
        low, high = match_score - 3, match_score + 5

    if rule_score == 0:
        low  -= 5
        high += 5

    return {
        "low":   round(max(0.0, low), 1),
        "high":  round(min(100.0, high), 1),
        "label": label,
    }


def build_match_result(match_score_result: dict, career_level: str) -> dict:
    """
    match_service.calculate_match_score()의 반환값을 최종 API 응답 형태로 조립한다.

    반환 형식:
    {
        "match_score":           72.5,
        "tech_score":            80.0,
        "trait_score":           65.0,
        "rule_score":            60.0,
        "confidence_interval":   {"low": 65.0, "high": 82.5, "label": "높음"},
        "matched_keywords":      [...],
        "unmatched_keywords":    [...],
        "trait_details":         [...],
        "rule_detail":           {...},
        "strengths":             [...],
        "weaknesses":            [...],
        "cl_points":             [...],
    }
    """
    match_score = match_score_result.get("match_score", 0.0)
    tech_score  = match_score_result.get("tech_score", 0.0)
    trait_score = match_score_result.get("trait_score", 0.0)
    rule_score  = match_score_result.get("rule_score", 0.0)

    ci = calc_confidence_interval(match_score, tech_score, trait_score, rule_score)

    return {
        **match_score_result,
        "confidence_interval": ci,
    }
