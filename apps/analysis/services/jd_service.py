"""
Pipeline 1 - ① JD 분석

역할:
  채용공고(JD) 텍스트를 읽고 매칭·갭 분석에 필요한 정보를 구조화해 추출한다.

포함 함수:
  extract_jd_keywords()     기술 스택 / 인재상 키워드 분리 추출 (구현 완료)
  extract_jd_requirements() 필수 조건 추출 — 연차·학력·직군
"""

import json
from .utils import get_client, clean_json


def extract_jd_keywords(jd_text: str) -> dict:
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
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 채용공고 분석 전문가입니다.\n"
                    "JD를 읽고 아래 두 가지로 키워드를 분리·추출하세요.\n\n"
                    "[tech_keywords] 기술 스택\n"
                    "- 프로그래밍 언어, 프레임워크, 라이브러리, 인프라, DB, 툴\n"
                    "- 원문 표기 그대로 사용 (예: 'React', 'Spring Boot', 'PostgreSQL')\n"
                    "- 동의어 중복 제거 (예: 'AWS'와 'Amazon Web Services' 중 하나만)\n\n"
                    "[trait_keywords] 인재상·역량\n"
                    "- 성격, 태도, 협업 방식, 소프트 스킬 등 기술이 아닌 역량 표현\n"
                    "- JD에 명시된 원문 문장/구 그대로 추출 (예: '주도적으로 문제를 해결하는 분')\n"
                    "- '우대사항' 중 기술이 아닌 항목도 포함\n"
                    "- 추상적 단어 단독 사용 금지 — 원문의 문맥 포함한 구/절 형태로 추출\n\n"
                    "공통 규칙:\n"
                    "- 회사명, 복지, 연봉 등 직무와 무관한 내용 제외\n"
                    "- 반드시 아래 JSON 형식으로만 응답. 마크다운 블록 금지.\n\n"
                    "{\n"
                    '  "tech_keywords":  ["Python", "Django", "Docker"],\n'
                    '  "trait_keywords": ["주도적으로 문제를 해결하는 분", "커뮤니케이션이 원활한 분"]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"아래 채용공고에서 기술 스택과 인재상·역량 키워드를 분리해 추출해주세요.\n\n"
                    f"[채용공고 JD]\n{jd_text}"
                ),
            },
        ],
    )
    raw    = clean_json(response.choices[0].message.content)
    result = json.loads(raw)

    return {
        "tech_keywords":  result.get("tech_keywords", []),
        "trait_keywords": result.get("trait_keywords", []),
    }


def extract_jd_requirements(jd_text: str) -> dict:
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
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 채용공고 분석 전문가입니다.\n"
                    "JD에서 지원 자격 요건을 정확하게 추출하세요.\n\n"
                    "추출 기준:\n"
                    "1. min_years (정수)\n"
                    "   - 명시된 최소 경력 연수. '신입', '경력 무관', '신입 가능' → 0\n"
                    "   - '3~5년' 같은 범위 표현 → 하한값(3) 사용\n"
                    "   - 명시 없으면 0\n\n"
                    "2. education (문자열)\n"
                    "   - '무관' | '고졸' | '대졸' | '석사이상' 중 하나\n"
                    "   - 학력 무관 또는 명시 없으면 '무관'\n\n"
                    "3. job_type (문자열)\n"
                    "   - 직군 키워드 (예: '백엔드', '프론트엔드', '풀스택', '데이터엔지니어', 'DevOps')\n"
                    "   - JD 직무 제목에서 추출. 불명확하면 빈 문자열\n\n"
                    "4. required_tech (배열)\n"
                    "   - '필수', '자격 요건', 'Required' 섹션의 기술만 포함\n"
                    "   - 원문 표기 그대로 사용\n\n"
                    "5. preferred_tech (배열)\n"
                    "   - '우대', '우대 사항', 'Preferred' 섹션의 기술만 포함\n"
                    "   - required_tech와 중복 제거\n\n"
                    "반드시 아래 JSON 형식으로만 응답하세요. 마크다운 블록 금지.\n"
                    "{\n"
                    '  "min_years":      0,\n'
                    '  "education":      "무관",\n'
                    '  "job_type":       "백엔드",\n'
                    '  "required_tech":  ["Python", "Django"],\n'
                    '  "preferred_tech": ["Kubernetes"]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"아래 채용공고에서 지원 자격 요건을 추출해주세요.\n\n"
                    f"[채용공고 JD]\n{jd_text}"
                ),
            },
        ],
    )
    raw    = clean_json(response.choices[0].message.content)
    result = json.loads(raw)

    return {
        "min_years":      int(result.get("min_years", 0)),
        "education":      result.get("education", "무관"),
        "job_type":       result.get("job_type", ""),
        "required_tech":  result.get("required_tech", []),
        "preferred_tech": result.get("preferred_tech", []),
    }
