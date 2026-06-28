"""
Pipeline 1 - ② 사용자 문서 분석 / 프로젝트 경험

역할:
  이력서·자소서에서 프로젝트 경험을 추출하고,
  GitHub 연동 데이터(나중에)와 병합해 최종 ProjectProfile을 만든다.
  Pipeline 1 ③의 ProjectScorer와 Pipeline 2 갭 분석에 입력값으로 사용된다.

포함 함수:
  extract_projects()    이력서·자소서에서 프로젝트 정보 추출 (미구현)
  merge_with_github()   GitHub 연동 데이터와 병합 — ProjectMerger
"""

from .github_service import analyze_repo, FRAMEWORK_ALIASES

# 분석 전체에서 실제로 가져올 repo 상한 (0 ~ MAX_REPOS).
# 입력 개수 검증은 input 앱 책임이고, 여기서는 "꺼내 쓸 때"의 안전망만 둔다.
MAX_REPOS = 5


def extract_projects(resume_text: str, cover_letter_text: str) -> list[dict]:
    """
    이력서·자소서에서 프로젝트 경험을 구조화해 추출한다.
    resume_service.analyze_resume()의 projects 필드보다 상세하게 추출한다.

    반환 형식 (ProjectProfile):
    [
        {
            "name":        "중고거래 플랫폼",
            "role":        "백엔드 리드",
            "tech":        ["Python", "Django", "PostgreSQL"],
            "domain":      "e-commerce",     # 도메인 분류 (gap 분석용)
            "team_size":   3,                 # 팀 규모
            "duration":    "3개월",           # 기간
            "contribution": 70,              # 기여도 (%) — 명시 없으면 null
            "result":      "MAU 1만 달성",
            "impact":      "high",           # "low" | "medium" | "high" — 임팩트 추정
            "is_github_verified": False,     # GitHub 연동 전까지 False 고정
            "github_url":  null,
        }
    ]

    TODO:
      - LLM 프롬프트 작성
        - domain 분류 기준 정의 (e-commerce, fintech, healthcare, logistics, social 등)
        - team_size / contribution / impact 추출 기준 정의
        - 명시되지 않은 필드는 null로 처리 (추측 금지)
      - resume_service.analyze_resume()의 projects 필드와 중복 여부 정리
        → 현재: analyze_resume()에서 name/role/tech/result만 추출
        → 방향: analyze_resume()는 가볍게 유지, 상세 추출은 이 함수로 위임
    """
    # TODO: 구현 필요
    raise NotImplementedError("extract_projects 미구현")


def _reconcile_tech(
    claimed: list[str],
    frameworks: set[str],
    languages: dict,
) -> tuple[list[str], list[str]]:
    """
    이력서 tech 주장을 repo 실제(frameworks + languages)와 대조한다.
    대소문자·별칭(패키지명 표기)을 흡수해 매칭한다.

    반환: (verified, unverified)
      verified   — repo에서 근거를 찾은 기술
      unverified — 이력서엔 있으나 repo에서 근거 못 찾은 기술 (질문의 금광)
    """
    fw_lower   = {f.lower() for f in frameworks}
    lang_lower = {l.lower() for l in languages}

    verified, unverified = [], []
    for tech in claimed:
        t = tech.strip().lower()
        # 이력서가 패키지명으로 적었을 수도 있어 별칭 정규화도 함께 시도
        normalized = FRAMEWORK_ALIASES.get(t, tech).lower()
        if t in fw_lower or normalized in fw_lower or t in lang_lower:
            verified.append(tech)
        else:
            unverified.append(tech)
    return verified, unverified


def _languages_to_pct(languages: dict) -> dict:
    """언어 바이트 수 → 백분율. 빈 dict면 그대로 빈 dict."""
    total = sum(languages.values())
    if not total:
        return {}
    return {lang: round(b / total * 100, 1) for lang, b in languages.items()}


def merge_with_github(projects: list[dict]) -> list[dict]:
    """
    추출된 ProjectProfile에 GitHub 실제 데이터를 병합한다 — ProjectMerger.

    각 project는 ProjectExperience.github_url에서 온 repo 링크를 들고 있다.
      project["github_urls"]  : list[str]  (1개 이상 — backend/frontend 분리 대비)
      project["github_url"]   : str        (단일 — ProjectExperience.github_url 직매핑 시)
    둘 중 있는 쪽을 사용하며, 여러 repo는 합산해 하나의 "실제 모습"으로 본다.

    ★ 전역 상한: 분석 전체에서 최대 MAX_REPOS(=5)개 repo만 실제로 가져온다.
       초과분은 에러 없이 github_errors에 kind="limit_skipped"로만 기록한다.
       (입력 개수 검증은 input 앱 책임 — 여기서는 꺼내 쓸 때의 안전망만)

    ★ 예외 안전: repo 연결 실패(비공개·삭제·오타·rate limit·네트워크)는
       project를 죽이지 않고 is_github_verified=False + github_errors로 흡수한다.
       전체 분석 파이프라인은 이력서 기반으로 계속 진행된다.

    각 project에 추가되는 필드:
      is_github_verified : bool   — repo 1개라도 분석 성공했는가
      github_urls        : list   — 사용한 repo 링크
      github_frameworks  : list   — repo에서 실제 검출된 프레임워크
      github_languages   : dict   — 언어 비중(%)
      verified_tech      : list   — 이력서 tech 중 repo로 검증된 것
      unverified_tech    : list   — 이력서 tech 중 근거 못 찾은 것
      github_evidence    : dict   — 프레임워크별 근거 파일
      github_errors      : list   — 실패한 repo 내역 [{github_url, error, kind}]
    """
    remaining = MAX_REPOS                  # 분석 전체에 걸친 전역 예산
    for project in projects:
        urls = project.get("github_urls")
        if not urls:
            single = project.get("github_url")
            urls = [single] if single else []

        # repo 링크가 아예 없는 프로젝트 — GitHub 검증 스킵 (정상 흐름)
        if not urls:
            project.setdefault("is_github_verified", False)
            project.setdefault("github_errors", [])
            continue

        # 전역 상한: 분석 전체에서 최대 MAX_REPOS개까지만 실제로 가져온다.
        # 초과분은 에러를 던지지 않고 limit_skipped로 기록 (분석은 계속 진행).
        use_urls   = urls[:remaining]
        over_limit = urls[len(use_urls):]
        remaining -= len(use_urls)

        all_frameworks: set[str] = set()
        all_languages: dict = {}
        evidence: dict = {}
        errors: list = []
        any_ok = False

        for url in use_urls:
            repo = analyze_repo(url)        # 절대 예외를 던지지 않음
            if not repo["ok"]:
                errors.append({
                    "github_url": url,
                    "error":      repo["error"],
                    "kind":       repo["error_kind"],
                })
                continue

            any_ok = True
            all_frameworks.update(repo["frameworks"])
            for lang, b in repo["languages"].items():
                all_languages[lang] = all_languages.get(lang, 0) + b
            for fw, files in repo["evidence"].items():
                evidence.setdefault(fw, [])
                evidence[fw].extend(f for f in files if f not in evidence[fw])

        for url in over_limit:
            errors.append({
                "github_url": url,
                "error":      f"분석 repo 상한({MAX_REPOS}개) 초과로 건너뜀.",
                "kind":       "limit_skipped",
            })

        claimed = project.get("tech") or project.get("tech_stack") or []
        verified, unverified = _reconcile_tech(claimed, all_frameworks, all_languages)

        project.update({
            "is_github_verified": any_ok,
            "github_urls":        urls,
            "github_frameworks":  sorted(all_frameworks),
            "github_languages":   _languages_to_pct(all_languages),
            "verified_tech":      verified,
            "unverified_tech":    unverified,
            "github_evidence":    evidence,
            "github_errors":      errors,    # 비어있으면 전부 성공
        })

    return projects


def score_projects(
    projects: list[dict],
    jd_tech_keywords: list[str],
    jd_domain: str | None = None,
) -> tuple[float, list[dict]]:
    """
    ProjectScorer: 각 프로젝트가 JD와 얼마나 관련 있는지 점수를 매기고,
    가장 관련성 높은 프로젝트(highlight_project)를 선정한다.

    채점 기준:
      - 기술 스택 매칭 점수 (집합 연산)
      - 도메인 일치 여부 (+보너스)
      - 팀 규모 / 기여도 / 임팩트
      - GitHub 검증 여부 (is_github_verified=True면 가산점)

    반환:
      project_score    : 0.0 ~ 100.0 (전체 프로젝트 종합)
      scored_projects  : 각 프로젝트에 score, is_highlight 필드 추가된 리스트

    TODO:
      - 채점 기준 가중치 정의
          tech_match_w : 0.5
          domain_w     : 0.2
          impact_w     : 0.2
          github_w     : 0.1
      - highlight_project 선정 기준 (가장 높은 score 1개)
      - extract_projects() 구현 후 연결
    """
    # TODO: 구현 필요
    raise NotImplementedError("score_projects 미구현")
