"""
Pipeline 2 - ③④ 갭 계산 + 결과 출력

역할:
  Pipeline 1의 JD 분석 결과와 사용자 문서 분석 결과를 재사용해
  구체적인 갭(부족한 부분)을 계산하고, 신입/경력에 따라 다른 메시지로 출력한다.

포함 함수:
  calculate_gap()      갭 항목 계산
  build_gap_message()  신입/경력 분기 메시지 생성
"""

from .match_service import EDUCATION_RANK


def calculate_gap(
    jd_keywords: dict,
    jd_requirements: dict,
    resume_analysis: dict,
    unmatched_keywords: list[str],
    trait_details: list[dict] | None = None,
) -> dict:
    """
    Pipeline 1의 결과를 재사용해 구체적인 갭 항목을 계산한다.

    반환 형식:
    {
        "missing_required_tech":  ["Kubernetes", "Kafka"],
        "missing_preferred_tech": ["Terraform"],
        "required_years":  3,
        "current_years":   1,
        "years_gap":       2,
        "education_ok":    True,
        "weak_traits": [
            {"trait": "주도적으로 문제를 해결하는 분", "similarity": 0.31}
        ]
    }
    """
    gap: dict = {}

    # 기술 갭
    req_tech  = {t.lower() for t in jd_requirements.get("required_tech", [])}
    pref_tech = {t.lower() for t in jd_requirements.get("preferred_tech", [])}
    unmatched = {k.lower() for k in unmatched_keywords}

    if req_tech:
        gap["missing_required_tech"]  = sorted(req_tech & unmatched)
        gap["missing_preferred_tech"] = sorted(pref_tech & unmatched)
    else:
        # required_tech 구분 없이 unmatched 전체를 missing으로
        gap["missing_required_tech"]  = sorted(unmatched)
        gap["missing_preferred_tech"] = []

    # 경력 갭
    min_years     = float(jd_requirements.get("min_years", 0))
    current_years = float(resume_analysis.get("years_of_experience", 0))
    gap["required_years"] = min_years
    gap["current_years"]  = current_years
    gap["years_gap"]      = round(min_years - current_years, 1)

    # 학력 갭
    req_edu = jd_requirements.get("education", "무관")
    cur_edu = resume_analysis.get("education", "대졸")
    gap["education_ok"] = (
        req_edu == "무관"
        or EDUCATION_RANK.get(cur_edu, 2) >= EDUCATION_RANK.get(req_edu, 2)
    )

    # 인재상 갭 (유사도 0.5 미만)
    gap["weak_traits"] = [
        {"trait": d["trait"], "similarity": d["similarity"]}
        for d in (trait_details or [])
        if d.get("similarity", 1.0) < 0.5
    ]

    return gap


def build_gap_message(gap_result: dict, career_level: str) -> dict:
    """
    calculate_gap()의 결과를 신입/경력에 따라 다른 톤의 메시지로 변환한다.

    entry       → "이것부터 준비해요" 톤
    experienced → "이 부분이 부족해요" 톤

    반환 형식:
    {
        "summary":      "한 줄 요약",
        "tech_gaps":    ["기술 갭 메시지1", ...],
        "career_gap":   "경력 갭 메시지 또는 None",
        "trait_gaps":   ["인재상 갭 메시지1", ...],
        "action_items": ["실천 항목1", ...]
    }
    """
    is_entry    = career_level == "entry"
    tech_prefix = "준비가 필요한 기술" if is_entry else "부족한 기술"

    missing_req  = gap_result.get("missing_required_tech", [])
    missing_pref = gap_result.get("missing_preferred_tech", [])
    years_gap    = gap_result.get("years_gap", 0)
    edu_ok       = gap_result.get("education_ok", True)
    weak_traits  = gap_result.get("weak_traits", [])

    # 기술 갭 메시지
    tech_gaps: list[str] = []
    for tech in missing_req:
        tech_gaps.append(
            f"{tech}: {'학습을 통해 역량을 쌓아두면 좋아요' if is_entry else '실무 경험이 부족합니다'} (필수)"
        )
    for tech in missing_pref:
        tech_gaps.append(
            f"{tech}: {'알아두면 경쟁력이 높아져요' if is_entry else '보유하면 우대 가능성이 높아집니다'} (우대)"
        )

    # 경력 갭 메시지
    career_gap: str | None = None
    if years_gap > 0:
        req  = gap_result.get("required_years", 0)
        curr = gap_result.get("current_years", 0)
        if is_entry:
            career_gap = (
                f"이 포지션은 {int(req)}년 이상 경력을 요구해요. "
                "프로젝트·인턴 경험으로 실무 역량을 증명해 보세요."
            )
        else:
            career_gap = (
                f"요구 경력({int(req)}년) 대비 {years_gap:.1f}년이 부족합니다. "
                "관련 프로젝트 경험을 강조해 보완하세요."
            )

    if not edu_ok:
        career_gap = (career_gap or "") + (
            " 학력 조건을 충족하지 못하고 있으니 참고하세요."
        )

    # 인재상 갭 메시지
    trait_gaps: list[str] = []
    for item in weak_traits:
        trait = item["trait"]
        if is_entry:
            trait_gaps.append(
                f"'{trait}' 역량이 자소서에 잘 드러나지 않아요. 관련 경험을 구체적으로 서술해 보세요."
            )
        else:
            trait_gaps.append(
                f"'{trait}' 역량이 충분히 어필되지 않고 있어요. 실무 사례를 추가해 보강하세요."
            )

    # 실천 항목
    action_items: list[str] = []
    for tech in missing_req[:3]:
        action_items.append(
            f"{tech} 공식 문서 학습 및 토이 프로젝트 적용" if is_entry
            else f"{tech} 실무 적용 경험 이력서에 추가"
        )
    for item in weak_traits[:2]:
        action_items.append(f"자소서에 '{item['trait']}' 관련 에피소드 보강")

    # 요약
    total_gaps = len(missing_req) + len(missing_pref) + (1 if years_gap > 0 else 0) + len(weak_traits)
    if total_gaps == 0:
        summary = "이 JD에 잘 맞는 프로필이에요! 면접 준비에 집중해 보세요." if is_entry \
                  else "이 포지션에 전반적으로 잘 부합합니다. 강점을 더 어필해 보세요."
    elif total_gaps <= 2:
        summary = "몇 가지만 보완하면 지원 경쟁력이 높아져요." if is_entry \
                  else "일부 항목에서 갭이 있지만 충분히 보완 가능한 수준입니다."
    else:
        summary = "준비가 필요한 항목이 있어요. 하나씩 채워나가 봐요!" if is_entry \
                  else "여러 항목에서 갭이 발견됩니다. 우선순위를 정해 보완하세요."

    return {
        "summary":      summary,
        "tech_gaps":    tech_gaps,
        "career_gap":   career_gap,
        "trait_gaps":   trait_gaps,
        "action_items": action_items,
    }
