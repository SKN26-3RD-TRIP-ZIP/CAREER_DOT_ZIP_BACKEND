"""
Pipeline 3 - ③ LLM 예상 질문 생성

역할:
  JD 분석 결과 + 이력서 + 자소서 + 프로젝트 경험을 바탕으로
  LLM이 맞춤형 면접 질문을 생성한다.
  각 질문에 source / basis 태그를 부착해 출처를 명확히 한다.

  기존 question_service.py의 _generate_questions()를 이 파일로 이관.

포함 함수:
  generate_questions()   LLM 기반 질문 생성 + source/basis 태그 부착
"""

import json
from .utils import get_client, clean_json


def generate_questions(
    job_role: str,
    company_name: str,
    jd_keywords: dict,
    resume_analysis: dict,
) -> list[dict]:
    """
    JD와 이력서 분석 결과를 바탕으로 LLM이 면접 질문을 생성한다.
    각 질문에 source(출처)와 basis(근거 원문 스니펫)를 함께 반환한다.

    반환 형식:
    [
        {
            "type":   "personality" | "technical" | "experience",
            "text":   "질문 내용",
            "source": "jd" | "resume" | "coverletter" | "project" | "combined",
            "basis":  "질문 생성 근거 원문 스니펫"
        },
        ...
    ]

    질문 유형별 기준:
      인성 (3개)   — 자소서 역량 문장(trait_evidence) 기반
      기술 (4개)   — JD 필수/우대 기술 스택(tech_keywords) 기반
      경험 (3개)   — 프로젝트 경험(projects) 기반
    """
    client = get_client()

    tech_keywords  = jd_keywords.get("tech_keywords", [])
    trait_keywords = jd_keywords.get("trait_keywords", [])
    experiences    = resume_analysis.get("key_experiences", [])
    projects       = resume_analysis.get("projects", [])
    trait_evidence = resume_analysis.get("trait_evidence", [])

    exp_str  = "\n".join(f"- {e}" for e in experiences)
    proj_str = "\n".join(
        f"- {p['name']}: {p.get('role', '')} / 기술: {', '.join(p.get('tech', []))} / 성과: {p.get('result', '')}"
        for p in projects
    )
    trait_str = "\n".join(f"- {t}" for t in trait_evidence)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.6,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 면접관입니다.\n"
                    "지원자의 이력서 분석 결과와 JD 키워드를 바탕으로 맞춤형 면접 질문을 생성합니다.\n\n"
                    "질문 유형별 기준:\n\n"
                    "[인성 질문 — 3개]\n"
                    "- 자소서 역량 증거 문장을 근거로 생성\n"
                    "- 지원자의 태도·협업 방식·가치관을 구체적으로 확인하는 질문\n\n"
                    "[기술 질문 — 4개]\n"
                    "- JD 기술 키워드에서 최소 2개 이상 반드시 포함\n"
                    "- 개념 설명형 1개, 실제 적용·트레이드오프 판단형 2개, 문제 상황 대응형 1개\n\n"
                    "[경험 기반 질문 — 3개]\n"
                    "- 프로젝트 경험에서 직접 인용해 질문 생성\n"
                    "- STAR 답변을 유도하는 형태\n\n"
                    "공통 규칙:\n"
                    "- 모든 질문은 한 문장으로 명확하게\n"
                    "- 각 질문마다 source(출처)와 basis(근거 스니펫) 반드시 명시\n"
                    "  source: 'jd' | 'resume' | 'coverletter' | 'project' | 'combined'\n"
                    "  basis:  질문 생성에 사용한 원문 키워드·문장 (1~2문장 이내)\n"
                    "- 반드시 아래 JSON 형식으로만 응답. 마크다운 블록 금지.\n\n"
                    "{\n"
                    '  "personality": [\n'
                    '    {"text": "질문", "source": "coverletter", "basis": "근거 원문"}\n'
                    '  ],\n'
                    '  "technical": [\n'
                    '    {"text": "질문", "source": "jd", "basis": "근거 원문"}\n'
                    '  ],\n'
                    '  "experience": [\n'
                    '    {"text": "질문", "source": "project", "basis": "근거 원문"}\n'
                    '  ]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[지원 직무] {job_role}\n"
                    f"[지원 회사] {company_name or '미입력'}\n"
                    f"[JD 기술 키워드] {', '.join(tech_keywords)}\n"
                    f"[JD 인재상·역량] {', '.join(trait_keywords)}\n\n"
                    f"[지원자 핵심 경험]\n{exp_str}\n\n"
                    f"[지원자 역량 증거 문장]\n{trait_str}\n\n"
                    f"[지원자 프로젝트]\n{proj_str}\n\n"
                    "위 정보를 최대한 반영해 인성 3개, 기술 4개, 경험 기반 3개 질문을 생성해주세요."
                ),
            },
        ],
    )

    data = json.loads(clean_json(response.choices[0].message.content))

    questions = []
    for q in data.get("personality", []):
        questions.append({
            "type":   "personality",
            "text":   q["text"],
            "source": q.get("source", "coverletter"),
            "basis":  q.get("basis", ""),
        })
    for q in data.get("technical", []):
        questions.append({
            "type":   "technical",
            "text":   q["text"],
            "source": q.get("source", "jd"),
            "basis":  q.get("basis", ""),
        })
    for q in data.get("experience", []):
        questions.append({
            "type":   "experience",
            "text":   q["text"],
            "source": q.get("source", "project"),
            "basis":  q.get("basis", ""),
        })

    return questions
