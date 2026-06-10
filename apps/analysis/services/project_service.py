"""
Pipeline 1 - ② 사용자 문서 분석 / 프로젝트 경험

역할:
  이력서·자소서에서 프로젝트 경험을 추출하고,
  GitHub 연동 데이터(나중에)와 병합해 최종 ProjectProfile을 만든다.
  Pipeline 1 ③의 ProjectScorer와 Pipeline 2 갭 분석에 입력값으로 사용된다.

포함 함수:
  extract_projects()    이력서·자소서에서 프로젝트 정보 추출 (미구현)
  merge_with_github()   GitHub 연동 데이터와 병합 — ProjectMerger (미구현, 나중에)
"""


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


def merge_with_github(
    projects: list[dict],
    github_username: str,
) -> list[dict]:
    """
    추출된 ProjectProfile에 GitHub 실제 데이터를 병합한다 — ProjectMerger.
    이력서에 적힌 기술 스택을 GitHub 커밋·언어 통계로 검증하고 신뢰도를 보강한다.

    반환: is_github_verified=True 항목이 포함된 ProjectProfile 리스트

    병합 로직 (예시):
      - GitHub repo 이름으로 이력서 프로젝트와 매칭
      - 매칭된 repo의 언어 통계 → tech 필드 검증
        (이력서에 Python이라 했는데 Python 비중이 낮으면 신뢰도 보통)
      - 커밋 수, 기여자 수 → contribution, team_size 보강
      - 최근 커밋일 → 현재 유지보수 여부

    TODO:
      - GitHub API 연동 (PyGitHub 또는 직접 REST 호출)
      - repo 이름 매칭 전략 (이름이 다를 수 있으므로 퍼지 매칭 필요)
      - 나중에 구현 예정 — 지금은 is_github_verified=False 고정
    """
    # TODO: 나중에 구현 (GitHub 연동 스프린트 시)
    raise NotImplementedError("merge_with_github 미구현 (GitHub 연동 스프린트 예정)")


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
