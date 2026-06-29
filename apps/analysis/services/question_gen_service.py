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
from .github_service import fetch_code_snippets, is_readme_file
from .analysis_prompt import (
    QUESTION_GEN_SYSTEM, build_question_gen_user,
    GITHUB_QUESTION_SYSTEM,
)


def generate_questions(
    job_role: str,
    company_name: str,
    jd_keywords: dict,
    resume_analysis: dict,
    rag_candidates: list[dict] | None = None,
    github_context: str = "",
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """
    JD와 이력서 분석 결과를 바탕으로 LLM이 면접 질문을 생성한다.
    rag_candidates가 있으면 질문 은행 후보를 참고 자료로 프롬프트에 주입한다.
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

    github_context: extract_interview_context()로 구축한 GitHub 컨텍스트 문자열.
                    있으면 JD/자소서 컨텍스트 뒤, 질문 생성 지시문 앞에 주입된다.
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

    rag_str = ""
    if rag_candidates:
        lines = []
        for c in rag_candidates[:10]:
            q_type = c.get("question_type", c.get("type", "technical"))
            text   = c.get("question_text", c.get("text", ""))
            if text:
                lines.append(f"- [{q_type}] {text}")
        if lines:
            rag_str = "\n".join(lines)

    rag_section = (
        f"\n[질문 은행 참고 후보 — 이 질문들의 패턴·유형을 참고해 더 맞춤화된 질문을 생성하세요]\n{rag_str}\n"
        if rag_str else ""
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0.6,
        messages=[
            {"role": "system", "content": QUESTION_GEN_SYSTEM},
            {"role": "user",   "content": build_question_gen_user(
                job_role, company_name, tech_keywords, trait_keywords,
                exp_str, trait_str, proj_str, rag_section, github_context,
            )},
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
    for q in data.get("talent", []):
        questions.append({
            "type":   "talent",
            "text":   q["text"],
            "source": q.get("source", "combined"),
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

    readme_str = snippets.pop("__readme__", "").strip() or "(README 없음)"
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
        f"[프로젝트 README]\n{readme_str}\n\n"
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
            {"role": "system", "content": GITHUB_QUESTION_SYSTEM},
            {"role": "user",   "content": context},
        ],
    )
    log_llm_usage(response)

    data = json.loads(clean_json(response.choices[0].message.content))

    questions = []
    for q in data.get("questions", []):
        q_type = q.get("type", "technical")
        if q_type not in ("technical", "experience"):
            q_type = "technical"
        source = q.get("source", "gitrepo")
        if source not in ("gitrepo", "combined"):
            source = "gitrepo"
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
