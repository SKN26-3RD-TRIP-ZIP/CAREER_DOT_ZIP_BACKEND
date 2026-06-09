"""
Pipeline 1 - ③ 비교 & 점수 산출

역할:
  JD 분석 결과(jd_service)와 사용자 문서 분석 결과(resume_service)를 비교해
  세 가지 점수를 산출하고 가중 합산하여 최종 매칭 점수를 반환한다.

포함 함수:
  _calc_tech_score()    기술 스펙 점수 — 집합 연산 커버리지 (구현 완료)
  _calc_trait_score()   역량 점수 — 임베딩 코사인 유사도 (구현 완료)
  _calc_rule_score()    룰베이스 점수 — 연차/학력/직군 조건 체크 (미구현)
  calculate_match_score() 세 점수 가중 합산 → 최종 점수 + LLM 강점/약점 (구현 완료, rule_score 연결 필요)
"""

import json
from .utils import get_client, clean_json, get_embeddings, cosine_similarity

# ────────────────────────────────────────────────────────
# 신입 / 경력별 가중치 정의
#
# tech_w  : 기술 스택 집합 연산 점수 비중
# trait_w : 인재상 임베딩 유사도 점수 비중
# rule_w  : 룰베이스(연차·학력·직군) 점수 비중
#
# TODO: rule_score 구현 후 rule_w 비중 반영 및 tech_w/trait_w 재조정 필요
# ────────────────────────────────────────────────────────
CAREER_WEIGHTS = {
    "entry":       {"tech_w": 0.40, "trait_w": 0.40, "rule_w": 0.20},
    "experienced": {"tech_w": 0.45, "trait_w": 0.20, "rule_w": 0.35},
}

EDUCATION_RANK: dict[str, int] = {"고졸": 1, "대졸": 2, "석사이상": 3, "무관": 0}

# 동일한 기술을 가리키는 별칭 정규화 테이블
TECH_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "node js": "node.js",
    "py": "python",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "mssql": "sql server",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "gcp": "google cloud",
    "aws": "amazon web services",
    "reactjs": "react",
    "react js": "react",
    "vuejs": "vue",
    "vue js": "vue",
    "springboot": "spring boot",
    "spring-boot": "spring boot",
}


def _normalize(keyword: str) -> str:
    """소문자 + 앞뒤 공백 제거 후 별칭 정규화."""
    k = keyword.lower().strip()
    return TECH_ALIASES.get(k, k)


def _calc_tech_score(
    tech_keywords: list[str],
    tech_stack: list[str],
) -> tuple[float, list[str], list[str]]:
    """
    기술 스펙 점수: JD 기술 키워드 대비 이력서 기술 스택 커버리지를 집합 연산으로 계산.

    - JD 기준으로 나누는 이유: "JD가 요구하는 기술 중 내가 얼마나 커버하는가"가 핵심
    - 표기 불일치(Postgres vs PostgreSQL 등)는 TECH_ALIASES 정규화로 보정

    Returns:
        tech_score         : 0.0 ~ 100.0
        matched_keywords   : 매칭된 키워드 목록 (근거 투명화)
        unmatched_keywords : JD에 있으나 이력서에 없는 키워드 (갭 분석 입력값)

    TODO:
      - extract_jd_requirements()가 구현되면 required_tech / preferred_tech 분리 처리
        (필수 미충족 시 감점 가중, 우대는 가산점 방식으로 개선)
    """
    if not tech_keywords:
        return 0.0, [], []

    jd_set     = {_normalize(k) for k in tech_keywords}
    resume_set = {_normalize(k) for k in tech_stack}

    matched   = jd_set & resume_set
    unmatched = jd_set - resume_set

    score = round(len(matched) / len(jd_set) * 100, 1)
    return score, sorted(matched), sorted(unmatched)


def _calc_trait_score(
    trait_keywords: list[str],
    trait_evidence: list[str],
    client,
) -> tuple[float, list[dict]]:
    """
    역량 점수: JD 인재상 키워드 vs 이력서·자소서 역량 증거 문장을
    임베딩 코사인 유사도로 비교한다.

    알고리즘:
      1. trait_keywords + trait_evidence 를 한 번에 임베딩
      2. 각 JD 인재상 항목에 대해 모든 증거 문장과 유사도 계산
      3. 가장 높은 유사도를 해당 항목 점수로 채택 (Max Pooling)
      4. 전체 인재상 항목의 평균 → trait_score (0.0 ~ 100.0)

    Returns:
        trait_score  : 0.0 ~ 100.0
        trait_details: 인재상별 매칭 근거 목록 (result_service / 디버깅용)
    """
    if not trait_keywords or not trait_evidence:
        return 0.0, []

    all_texts      = trait_keywords + trait_evidence
    all_embeddings = get_embeddings(all_texts, client)

    kw_vecs = all_embeddings[:len(trait_keywords)]
    ev_vecs = all_embeddings[len(trait_keywords):]

    trait_details = []
    scores        = []

    for kw, kw_vec in zip(trait_keywords, kw_vecs):
        sims     = [cosine_similarity(kw_vec, ev_vec) for ev_vec in ev_vecs]
        best_idx = sims.index(max(sims))
        best_sim = sims[best_idx]
        scores.append(best_sim)
        trait_details.append({
            "trait":      kw,
            "best_match": trait_evidence[best_idx],
            "similarity": round(best_sim, 4),
        })

    trait_score = round((sum(scores) / len(scores)) * 100, 1)
    return trait_score, trait_details


def _calc_rule_score(
    jd_requirements: dict,
    resume_analysis: dict,
    job_role: str = "",
) -> tuple[float, dict]:
    """
    룰베이스 점수: 연차·학력·직군 등 정량 조건을 규칙으로 체크한다.
    gap_service의 갭 계산과 입력/출력을 공유한다.

    기대 입력 (extract_jd_requirements 구현 후 연결):
      jd_requirements = {
          "min_years":      3,
          "education":      "대졸",
          "job_type":       "백엔드",
          "required_tech":  ["Python", "Django"],
          "preferred_tech": ["Kubernetes"],
      }
      resume_analysis = {
          ...현재 필드들...,
          "years_of_experience": 2,   # TODO: resume_service에서 추출
          "education":           "대졸",
          "career_level":        "entry",
      }

    반환 형식 (예시):
      rule_score = 60.0
      rule_detail = {
          "years_gap":       -1,       # 요구 연차 - 보유 연차 (음수면 초과 충족)
          "education_ok":    True,
          "job_type_match":  True,
      }

    """
    if not jd_requirements:
        return 0.0, {}

    score  = 0.0
    detail: dict = {}

    # 연차 (최대 40점)
    min_years     = float(jd_requirements.get("min_years", 0))
    current_years = float(resume_analysis.get("years_of_experience", 0))
    years_gap     = min_years - current_years
    years_score   = max(0.0, 40.0 - max(0.0, years_gap) * 10)
    score += years_score
    detail["years_gap"]   = round(years_gap, 1)
    detail["years_score"] = round(years_score, 1)

    # 학력 (30점)
    req_edu  = jd_requirements.get("education", "무관")
    cur_edu  = resume_analysis.get("education", "대졸")
    edu_ok   = (
        req_edu == "무관"
        or EDUCATION_RANK.get(cur_edu, 2) >= EDUCATION_RANK.get(req_edu, 2)
    )
    edu_score = 30.0 if edu_ok else 0.0
    score += edu_score
    detail["education_ok"]  = edu_ok
    detail["edu_score"]     = edu_score

    # 직군 일치 (30점) — JD job_type 키워드가 job_role에 포함되는지 비교
    req_job_type   = jd_requirements.get("job_type", "").lower()
    job_role_lower = job_role.lower()
    job_match      = bool(req_job_type) and (
        req_job_type in job_role_lower or job_role_lower in req_job_type
    )
    job_score = 30.0 if job_match else 0.0
    score += job_score
    detail["job_type_match"] = job_match
    detail["job_score"]      = job_score

    return round(score, 1), detail


def calculate_match_score(
    jd_keywords: dict,
    resume_analysis: dict,
    cover_letter_text: str = "",
    career_level: str = "entry",
    jd_requirements: dict | None = None,
    job_role: str = "",
) -> dict:
    """
    세 가지 점수를 가중 합산하여 최종 매칭 점수를 반환한다.
    LLM은 점수 계산에서 제외하고 강점·약점·자소서 포인트 서술에만 사용한다.

    점수 산출:
      tech_score  = _calc_tech_score()  — 집합 연산
      trait_score = _calc_trait_score() — 임베딩 유사도
      rule_score  = _calc_rule_score()  — 룰베이스 (현재 0점 고정, 구현 후 활성화)
      match_score = tech_score × tech_w + trait_score × trait_w + rule_score × rule_w

    반환 형식:
    {
        "match_score":        72.5,
        "tech_score":         80.0,
        "trait_score":        65.0,
        "rule_score":         0.0,        # TODO: 룰베이스 구현 후 반영
        "matched_keywords":   ["python", "django"],
        "unmatched_keywords": ["kubernetes", "kafka"],
        "trait_details":      [{"trait": "...", "best_match": "...", "similarity": 0.82}],
        "rule_detail":        {},         # TODO: 룰베이스 구현 후 반영
        "strengths":          ["강점1", "강점2"],
        "weaknesses":         ["약점1", "약점2"],
        "cl_points":          ["자소서 반영 포인트1", "포인트2"]
    }
    """
    client = get_client()

    tech_keywords  = jd_keywords.get("tech_keywords", [])
    trait_keywords = jd_keywords.get("trait_keywords", [])

    tech_stack     = resume_analysis.get("tech_stack", [])
    experiences    = resume_analysis.get("key_experiences", [])
    strengths_raw  = resume_analysis.get("strengths", [])
    projects       = resume_analysis.get("projects", [])
    trait_evidence = resume_analysis.get("trait_evidence", [])

    # 1. 기술 스펙 점수
    tech_score, matched_keywords, unmatched_keywords = _calc_tech_score(
        tech_keywords, tech_stack
    )

    # 2. 역량 점수
    trait_score, trait_details = _calc_trait_score(
        trait_keywords, trait_evidence, client
    )

    # 3. 룰베이스 점수
    rule_score, rule_detail = _calc_rule_score(
        jd_requirements or {}, resume_analysis, job_role
    )

    # 4. 최종 가중 합산
    weights     = CAREER_WEIGHTS.get(career_level, CAREER_WEIGHTS["entry"])
    match_score = round(
        tech_score  * weights["tech_w"]  +
        trait_score * weights["trait_w"] +
        rule_score  * weights["rule_w"],
        1,
    )

    # 5. LLM: 강점·약점·자소서 포인트 서술
    proj_str = "\n".join(
        f"- {p['name']}: {p.get('role', '')} / 기술: {', '.join(p.get('tech', []))} / 성과: {p.get('result', '')}"
        for p in projects
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 채용 매칭 전문가입니다.\n"
                    "JD 요구사항과 지원자 이력서를 비교 분석해 강점·약점·자소서 포인트를 제공합니다.\n\n"
                    "분석 기준:\n"
                    "1. strengths: JD 요구사항(기술·인재상 모두)과 일치하는 지원자의 강점 (최대 5개)\n"
                    "2. weaknesses: JD에서 요구하지만 이력서에 부족한 역량 (최대 5개)\n"
                    "3. cl_points: 자소서에서 면접에 활용할 수 있는 핵심 포인트 (최대 3개)\n\n"
                    "반드시 아래 JSON 형식으로만 응답하세요. 마크다운 블록 금지.\n"
                    "{\n"
                    '  "strengths":  ["강점1", "강점2"],\n'
                    '  "weaknesses": ["약점1", "약점2"],\n'
                    '  "cl_points":  ["포인트1", "포인트2"]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[JD 기술 키워드]\n{', '.join(tech_keywords) or '없음'}\n\n"
                    f"[JD 인재상·역량]\n{chr(10).join(f'- {t}' for t in trait_keywords) or '없음'}\n\n"
                    f"[매칭된 기술 키워드]\n{', '.join(matched_keywords) or '없음'}\n\n"
                    f"[부족한 기술 키워드]\n{', '.join(unmatched_keywords) or '없음'}\n\n"
                    f"[지원자 기술 스택]\n{', '.join(tech_stack)}\n\n"
                    f"[핵심 경험]\n" + "\n".join(f"- {e}" for e in experiences) + "\n\n"
                    f"[역량 증거 문장]\n" + "\n".join(f"- {e}" for e in trait_evidence) + "\n\n"
                    f"[강점]\n" + "\n".join(f"- {s}" for s in strengths_raw) + "\n\n"
                    f"[프로젝트]\n{proj_str}\n\n"
                    f"[자기소개서 요약]\n{cover_letter_text[:500] if cover_letter_text else '미입력'}\n\n"
                    "위 정보를 바탕으로 강점·약점·자소서 포인트를 분석해주세요."
                ),
            },
        ],
    )

    raw        = clean_json(response.choices[0].message.content)
    llm_result = json.loads(raw)

    return {
        "match_score":        match_score,
        "tech_score":         tech_score,
        "trait_score":        trait_score,
        "rule_score":         rule_score,
        "matched_keywords":   matched_keywords,
        "unmatched_keywords": unmatched_keywords,
        "trait_details":      trait_details,
        "rule_detail":        rule_detail,
        **llm_result,
    }
