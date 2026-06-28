"""
Pipeline 1 - ② 사용자 문서 분석

역할:
  이력서·자기소개서를 읽고 매칭·갭 분석에 필요한 지원자 정보를 구조화해 추출한다.

포함 함수:
  analyze_resume()  이력서 + 자소서 통합 분석
"""

import json
from .utils import get_client, clean_json, log_llm_usage
from .analysis_prompt import RESUME_ANALYSIS_SYSTEM, build_resume_analysis_user


def analyze_resume(resume_text: str, cover_letter_text: str, model: str = "gpt-4o-mini") -> dict:
    """
    이력서 + 자기소개서를 분석해 구조화된 딕셔너리로 반환한다.

    반환 형식:
    {
        # ─ 기술 분석 ─────────────────────────────────────────
        "tech_stack":        ["Python", "Django"],

        # ─ 경험 분석 ─────────────────────────────────────────
        "key_experiences":   ["3인 팀에서 백엔드 리드로 REST API 15개 설계"],
        "projects": [
            {
                "name":   "커머스 플랫폼",
                "role":   "백엔드 개발",
                "tech":   ["Python", "Django"],
                "result": "MAU 1만 달성",
                "domain": "e-commerce"
            }
        ],

        # ─ 역량·인재상 분석 ───────────────────────────────────
        "strengths":         ["데이터 기반 의사결정 (A/B 테스트 경험 보유)"],
        "trait_evidence":    ["의견 충돌 시 데이터를 근거로 설득해 팀 합의를 이끌어낸 경험"],

        # ─ 자격 조건 분석 (룰베이스 점수용) ─────────────────
        "years_of_experience": 2,        # 실무 경력 연수 (정규직·계약직·인턴 합산)
        "education":           "대졸",   # 최종 학력 ("고졸" | "대졸" | "석사이상")
        "career_level":        "entry",  # 이력서 기반 자동 추론 ("entry" | "experienced")
    }
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": RESUME_ANALYSIS_SYSTEM},
            {"role": "user",   "content": build_resume_analysis_user(resume_text, cover_letter_text)},
        ],
    )
    log_llm_usage(response)
    raw = clean_json(response.choices[0].message.content)
    return json.loads(raw)
