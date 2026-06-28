"""
Pipeline 1 - ① JD 분석

역할:
  채용공고(JD) 텍스트를 읽고 매칭·갭 분석에 필요한 정보를 구조화해 추출한다.

포함 함수:
  extract_jd_keywords()     기술 스택 / 인재상 키워드 분리 추출 (구현 완료)
  extract_jd_requirements() 필수 조건 추출 — 연차·학력·직군
"""

import json
from .utils import get_client, clean_json, log_llm_usage
from .analysis_prompt import (
    JD_KEYWORDS_SYSTEM, build_jd_keywords_user,
    JD_REQUIREMENTS_SYSTEM, build_jd_requirements_user,
)


def extract_jd_keywords(jd_text: str, model: str = "gpt-4o-mini") -> dict:
    """
    JD 텍스트에서 기술 스택 키워드와 인재상·역량 키워드를 분리 추출한다.

    반환 형식:
    {
        "tech_keywords":  ["Python", "Django", "Docker"],
        "trait_keywords": ["주도적으로 문제를 해결하는 분", "커뮤니케이션이 원활한 분"]
    }
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": JD_KEYWORDS_SYSTEM},
            {"role": "user",   "content": build_jd_keywords_user(jd_text)},
        ],
    )
    log_llm_usage(response)
    raw    = clean_json(response.choices[0].message.content)
    result = json.loads(raw)

    return {
        "tech_keywords":  result.get("tech_keywords", []),
        "trait_keywords": result.get("trait_keywords", []),
    }


def extract_jd_requirements(jd_text: str, model: str = "gpt-4o-mini") -> dict:
    """
    JD 텍스트에서 지원 자격 요건(필수 조건)을 추출한다.
    match_service의 룰베이스 점수 및 gap_service의 갭 계산에 사용된다.

    반환 형식 (예시):
    {
        "min_years":   3,          # 최소 경력 연차 (신입이면 0)
        "education":  "대졸",      # 최소 학력 ("무관" | "고졸" | "대졸" | "석사이상")
        "job_type":   "백엔드",    # 직군 키워드
        "required_tech": ["Python", "Django"],  # 필수(must-have) 기술 — 우대와 분리
        "preferred_tech": ["Kubernetes"]        # 우대(nice-to-have) 기술
    }

    """
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": JD_REQUIREMENTS_SYSTEM},
            {"role": "user",   "content": build_jd_requirements_user(jd_text)},
        ],
    )
    log_llm_usage(response)
    raw    = clean_json(response.choices[0].message.content)
    result = json.loads(raw)

    return {
        "min_years":      int(result.get("min_years", 0)),
        "education":      result.get("education", "무관"),
        "job_type":       result.get("job_type", ""),
        "required_tech":  result.get("required_tech", []),
        "preferred_tech": result.get("preferred_tech", []),
    }
