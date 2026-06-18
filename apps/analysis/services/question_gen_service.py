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
from .utils import get_client, clean_json, log_llm_usage
from .github_service import fetch_code_snippets


def generate_questions(
    job_role: str,
    company_name: str,
    jd_keywords: dict,
    resume_analysis: dict,
    model: str = "gpt-4o-mini",
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
        model=model,
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
    log_llm_usage(response)

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


# ══════════════════════════════════════════════════════════════
# GitHub repo 기반 심화 질문 (repo + 이력서 + 자소서 결합)
#
#   merge_with_github() 결과 project를 입력으로 받아,
#   이력서 주장·자소서 역량 문장·실제 코드를 교차 대조해 질문을 만든다.
#
#   질문 갈래:
#     ① 미검증 추궁  — unverified_tech (이력서엔 있으나 repo 근거 없음)
#     ② 자소서 교차  — 자소서 역량 주장 ↔ repo 실제 (source="combined")
#     ③ 코드 심화    — 실제 소스 스니펫의 설계 의도
# ══════════════════════════════════════════════════════════════

def _build_github_context(
    project: dict,
    snippets: dict,
    resume_analysis: dict | None = None,
    cover_letter_text: str = "",
) -> str:
    """LLM에 넣을 'GitHub 대조 컨텍스트' 문자열. (순수 함수, 네트워크 없음)"""
    resume_analysis = resume_analysis or {}

    claimed      = project.get("tech") or project.get("tech_stack") or []
    verified     = project.get("verified_tech", [])
    unverified   = project.get("unverified_tech", [])
    frameworks   = project.get("github_frameworks", [])
    languages    = project.get("github_languages", {})
    contribution = project.get("contribution")

    experiences    = resume_analysis.get("key_experiences", [])
    trait_evidence = resume_analysis.get("trait_evidence", [])

    lang_str    = ", ".join(f"{k} {v}%" for k, v in languages.items()) or "정보 없음"
    exp_str     = "\n".join(f"- {e}" for e in experiences) or "(없음)"
    trait_str   = "\n".join(f"- {t}" for t in trait_evidence) or "(없음)"
    cl_snippet  = (cover_letter_text or "").strip()[:600] or "(자소서 없음)"
    snippet_str = "\n\n".join(
        f"--- {path} ---\n{code}" for path, code in snippets.items()
    ) or "(코드 스니펫 없음)"

    return (
        f"[프로젝트] {project.get('name', '이름 미상')}\n"
        f"[이력서가 주장한 기술] {', '.join(claimed) or '없음'}\n"
        f"[이력서 기여도 주장] {contribution if contribution is not None else '미입력'}\n"
        f"[repo로 검증된 기술] {', '.join(verified) or '없음'}\n"
        f"[repo에서 근거 못 찾은 기술] {', '.join(unverified) or '없음'}\n"
        f"[repo 실제 프레임워크] {', '.join(frameworks) or '없음'}\n"
        f"[repo 언어 비중] {lang_str}\n\n"
        f"[이력서 핵심 경험]\n{exp_str}\n\n"
        f"[자소서 역량 증거 문장]\n{trait_str}\n\n"
        f"[자소서 원문 일부]\n{cl_snippet}\n\n"
        f"[핵심 소스 코드]\n{snippet_str}"
    )


def generate_github_questions(
    project: dict,
    resume_analysis: dict | None = None,
    cover_letter_text: str = "",
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """
    GitHub 검증 결과(merge_with_github 출력) + 이력서 + 자소서를 결합해
    코드 기반 심화 질문을 생성한다.

    반환:
        [{ "type": "technical"|"experience", "text": ..., "source": "project"|"combined", "basis": ... }, ...]

    ★ repo를 하나도 못 읽었으면(is_github_verified=False) 빈 리스트 반환 —
      코드 근거가 없으니 GitHub 전용 질문을 만들지 않는다.
    """
    if not project.get("is_github_verified"):
        return []

    # 코드 심화 질문용 스니펫 (예외 안전 — 실패해도 {} 반환되어 질문은 계속)
    snippets: dict = {}
    for url in project.get("github_urls", []):
        snippets.update(fetch_code_snippets(url))
        if len(snippets) >= 4:
            break

    context = _build_github_context(project, snippets, resume_analysis, cover_letter_text)
    client = get_client()

    response = client.chat.completions.create(
        model=model,
        temperature=0.5,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 지원자의 GitHub repo를 직접 읽고 이력서·자소서와 대조하는 기술 면접관입니다.\n"
                    "세 자료의 차이를 근거로 날카로운 심화 질문 3개를 생성하세요.\n\n"
                    "[질문 구성 — 우선순위 순]\n"
                    "1. (technical, source=project) repo에서 근거 못 찾은 기술의 실제 사용 여부 확인\n"
                    "   예: 'Redis를 사용했다고 하셨는데 repo에서 흔적을 찾지 못했습니다. 어디에 적용하셨나요?'\n"
                    "2. (technical 또는 experience, source=combined) 자소서 역량 주장 ↔ 실제 코드 교차 검증\n"
                    "   예: '자소서에 성능 최적화를 주도했다고 쓰셨는데, repo의 어느 부분이 그 작업인가요?'\n"
                    "3. (technical, source=project) 실제 소스 코드의 설계 의도 (스니펫 있을 때만)\n\n"
                    "[규칙]\n"
                    "- 근거 못 찾은 기술이 없으면 1번 대신 코드 심화/자소서 교차 질문을 늘리세요.\n"
                    "- 추측으로 단정하지 말고 '확인'하는 어조로 (해명할 여지를 줄 것).\n"
                    "- 자소서 내용을 실제로 인용해 만든 질문만 source=combined, 그 외는 source=project.\n"
                    "- 모든 질문은 한 문장, 물음표로 끝나게. 각 질문에 basis로 근거 명시.\n"
                    "- 반드시 아래 JSON으로만 응답. 마크다운 금지.\n\n"
                    "{\n"
                    '  "questions": [\n'
                    '    {"type": "technical", "source": "project", "text": "질문", "basis": "근거 (예: 미검증 Redis / models.py)"}\n'
                    "  ]\n"
                    "}"
                ),
            },
            {"role": "user", "content": context},
        ],
    )
    log_llm_usage(response)

    data = json.loads(clean_json(response.choices[0].message.content))

    questions = []
    for q in data.get("questions", []):
        q_type = q.get("type", "technical")
        if q_type not in ("technical", "experience"):
            q_type = "technical"
        source = q.get("source", "project")
        if source not in ("project", "combined"):
            source = "project"
        questions.append({
            "type":   q_type,
            "text":   q["text"],
            "source": source,
            "basis":  q.get("basis", ""),
        })

    return questions


def generate_github_questions_for_projects(
    projects: list[dict],
    resume_analysis: dict | None = None,
    cover_letter_text: str = "",
    max_total: int = 3,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """
    여러 프로젝트에 대해 GitHub 질문을 생성하고 전체 max_total개로 캡한다.
    검증 성공(is_github_verified)한 프로젝트만 대상으로 한다.

    오케스트레이터(question_service)가 호출하는 진입점.
    repo가 하나도 검증 안 됐으면 빈 리스트.
    """
    collected: list[dict] = []
    for project in projects or []:
        if not project.get("is_github_verified"):
            continue
        collected.extend(
            generate_github_questions(project, resume_analysis, cover_letter_text, model)
        )
        if len(collected) >= max_total:
            break
    return collected[:max_total]
