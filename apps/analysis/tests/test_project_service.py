"""
project_service 단위 테스트

테스트 대상:
  extract_projects()    이력서·자소서에서 프로젝트 정보 추출 — 미구현 (NotImplementedError)
  merge_with_github()   GitHub 연동 데이터 병합 — 미구현 (NotImplementedError)
  score_projects()      프로젝트 JD 관련성 점수 계산 — 미구현 (NotImplementedError)

참고:
  세 함수 모두 NotImplementedError를 발생시킵니다.
  함수가 구현되면 아래 TODO 테스트를 채워주세요.

실행:
  pytest apps/analysis/tests/test_project_service.py -v
"""

import pytest
from apps.analysis.services.project_service import (
    extract_projects,
    merge_with_github,
    score_projects,
)


# ══════════════════════════════════════════════════════════════
# 미구현 함수 — NotImplementedError 확인
# ══════════════════════════════════════════════════════════════

class TestNotImplemented:

    def test_extract_projects_미구현(self):
        with pytest.raises(NotImplementedError):
            extract_projects("이력서 내용", "자소서 내용")

    def test_merge_with_github_미구현(self):
        with pytest.raises(NotImplementedError):
            merge_with_github([], "github_user")

    def test_score_projects_미구현(self):
        with pytest.raises(NotImplementedError):
            score_projects([], ["Python", "Django"])


# ══════════════════════════════════════════════════════════════
# TODO: extract_projects 구현 후 아래 테스트 채우기
# ══════════════════════════════════════════════════════════════

# class TestExtractProjects:
#
#     RESUME_WITH_PROJECTS = """
#     [프로젝트]
#     - 중고거래 플랫폼 (팀 3인, 백엔드 리드, 2024.09~2024.12, 기여도 70%)
#       - Python, Django, PostgreSQL 사용
#       - MAU 1만 달성
#     - 핀테크 사이드프로젝트 (개인, 2024.01~2024.06)
#       - FastAPI, Redis 사용
#       - 앱스토어 출시
#     """
#
#     def test_기본_구조(self):
#         result = extract_projects(self.RESUME_WITH_PROJECTS, "자소서")
#         assert isinstance(result, list)
#         assert len(result) > 0
#
#     def test_필수_필드_존재(self):
#         result = extract_projects(self.RESUME_WITH_PROJECTS, "자소서")
#         required = {"name", "role", "tech", "domain", "team_size", "duration", "result", "impact", "is_github_verified"}
#         for p in result:
#             missing = required - set(p.keys())
#             assert not missing, f"프로젝트 필드 누락: {missing}"
#
#     def test_is_github_verified_false_기본값(self):
#         result = extract_projects(self.RESUME_WITH_PROJECTS, "")
#         for p in result:
#             assert p["is_github_verified"] == False
#
#     def test_tech_배열_형식(self):
#         result = extract_projects(self.RESUME_WITH_PROJECTS, "")
#         for p in result:
#             assert isinstance(p["tech"], list)
#
#     def test_기여도_없으면_null(self):
#         resume_no_contribution = """
#         [프로젝트]
#         - 개인 프로젝트 (2024.01~2024.06)
#           - Python 사용
#         """
#         result = extract_projects(resume_no_contribution, "")
#         # 명시 없으면 contribution이 null이어야 함
#         for p in result:
#             # contribution이 없거나 None이어야 함
#             pass  # 구현 후 채우기


# ══════════════════════════════════════════════════════════════
# TODO: score_projects 구현 후 아래 테스트 채우기
# ══════════════════════════════════════════════════════════════

# class TestScoreProjects:
#
#     PROJECTS = [
#         {
#             "name": "커머스플랫폼",
#             "role": "백엔드 리드",
#             "tech": ["Python", "Django", "Redis"],
#             "domain": "e-commerce",
#             "team_size": 3,
#             "duration": "6개월",
#             "contribution": 70,
#             "result": "MAU 1만",
#             "impact": "high",
#             "is_github_verified": True,
#             "github_url": None,
#         },
#         {
#             "name": "사이드프로젝트",
#             "role": "개인 개발",
#             "tech": ["FastAPI"],
#             "domain": "productivity",
#             "team_size": 1,
#             "duration": "3개월",
#             "contribution": 100,
#             "result": "앱스토어 출시",
#             "impact": "medium",
#             "is_github_verified": False,
#             "github_url": None,
#         },
#     ]
#
#     def test_반환_형식(self):
#         score, scored = score_projects(self.PROJECTS, ["Python", "Django"])
#         assert isinstance(score, float)
#         assert 0.0 <= score <= 100.0
#         assert isinstance(scored, list)
#         assert len(scored) == len(self.PROJECTS)
#
#     def test_score_highlight_필드(self):
#         _, scored = score_projects(self.PROJECTS, ["Python", "Django"])
#         for p in scored:
#             assert "score" in p
#             assert "is_highlight" in p
#
#     def test_기술_매칭_높은_프로젝트가_highlight(self):
#         _, scored = score_projects(self.PROJECTS, ["Python", "Django", "Redis"])
#         highlighted = [p for p in scored if p["is_highlight"]]
#         assert len(highlighted) == 1
#         # Python/Django/Redis를 모두 사용한 커머스플랫폼이 highlight여야 함
#         assert highlighted[0]["name"] == "커머스플랫폼"
