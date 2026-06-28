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

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from unittest.mock import patch
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

    def test_score_projects_미구현(self):
        with pytest.raises(NotImplementedError):
            score_projects([], ["Python", "Django"])


# ══════════════════════════════════════════════════════════════
# merge_with_github — GitHub repo 검증 병합 (analyze_repo 모킹)
#   ★ 예외 안전성 중심: 연결 실패해도 전체가 죽지 않는지 확인
# ══════════════════════════════════════════════════════════════

def _ok_repo(url, frameworks, languages=None, evidence=None):
    return {
        "github_url": url, "ok": True, "error": None, "error_kind": None,
        "frameworks": frameworks, "raw_packages": [], "evidence": evidence or {},
        "languages": languages or {},
    }


def _fail_repo(url, kind, msg):
    return {
        "github_url": url, "ok": False, "error": msg, "error_kind": kind,
        "frameworks": [], "raw_packages": [], "evidence": {}, "languages": {},
    }


class TestMergeWithGithub:

    PATCH = "apps.analysis.services.project_service.analyze_repo"

    def test_repo_없으면_검증_스킵(self):
        projects = [{"name": "P", "tech": ["Python"]}]
        result = merge_with_github(projects)
        assert result[0]["is_github_verified"] is False
        assert result[0]["github_errors"] == []

    def test_tech_검증_verified_unverified_분리(self):
        projects = [{
            "name": "마켓", "tech": ["Django", "Redis"],
            "github_url": "https://github.com/u/market",
        }]
        with patch(self.PATCH, return_value=_ok_repo(
            "https://github.com/u/market", ["Django"], {"Python": 1000}
        )):
            result = merge_with_github(projects)
        p = result[0]
        assert p["is_github_verified"] is True
        assert "Django" in p["verified_tech"]
        assert "Redis" in p["unverified_tech"]      # repo에 근거 없음 → 추궁 질문감

    def test_언어로도_검증됨(self):
        # "Python"은 프레임워크가 아니라 언어통계로 검증되어야 함
        projects = [{"name": "P", "tech": ["Python"],
                     "github_url": "https://github.com/u/p"}]
        with patch(self.PATCH, return_value=_ok_repo(
            "https://github.com/u/p", [], {"Python": 5000}
        )):
            result = merge_with_github(projects)
        assert "Python" in result[0]["verified_tech"]

    def test_repo_여러개_합산(self):
        projects = [{
            "name": "풀스택", "tech": ["Django", "React"],
            "github_urls": ["https://github.com/u/be", "https://github.com/u/fe"],
        }]
        def side(url):
            if url.endswith("/be"):
                return _ok_repo(url, ["Django"], {"Python": 1000})
            return _ok_repo(url, ["React"], {"JavaScript": 500})
        with patch(self.PATCH, side_effect=side):
            result = merge_with_github(projects)
        assert set(result[0]["verified_tech"]) == {"Django", "React"}

    # ── 예외 안전성 ──

    def test_연결실패해도_전체_안죽음(self):
        projects = [{"name": "P", "tech": ["Django"],
                     "github_url": "https://github.com/u/private"}]
        with patch(self.PATCH, return_value=_fail_repo(
            "https://github.com/u/private", "not_found",
            "repo를 찾을 수 없습니다 (비공개·삭제·URL 오타).",
        )):
            result = merge_with_github(projects)      # 예외 안 터져야 함
        p = result[0]
        assert p["is_github_verified"] is False
        assert p["github_errors"][0]["kind"] == "not_found"
        assert "Django" in p["unverified_tech"]       # 검증 못 했으니 미검증으로

    def test_일부_repo만_실패시_부분성공(self):
        projects = [{
            "name": "풀스택", "tech": ["Django", "React"],
            "github_urls": ["https://github.com/u/be", "https://github.com/u/fe"],
        }]
        def side(url):
            if url.endswith("/be"):
                return _ok_repo(url, ["Django"], {"Python": 1000})
            return _fail_repo(url, "rate_limit", "한도 초과")
        with patch(self.PATCH, side_effect=side):
            result = merge_with_github(projects)
        p = result[0]
        assert p["is_github_verified"] is True        # be가 성공했으므로 True
        assert "Django" in p["verified_tech"]
        assert "React" in p["unverified_tech"]        # fe 실패 → React 미검증
        assert len(p["github_errors"]) == 1

    def test_여러_프로젝트_독립처리(self):
        projects = [
            {"name": "A", "tech": ["Django"], "github_url": "https://github.com/u/a"},
            {"name": "B", "tech": ["React"],  "github_url": "https://github.com/u/b"},
        ]
        def side(url):
            if url.endswith("/a"):
                return _ok_repo(url, ["Django"])
            return _fail_repo(url, "network", "연결 실패")
        with patch(self.PATCH, side_effect=side):
            result = merge_with_github(projects)
        assert result[0]["is_github_verified"] is True
        assert result[1]["is_github_verified"] is False

    # ── 전역 상한 (분석 전체 합산 최대 5개) ──

    def test_전역_상한_5개_초과분은_분석_안함(self):
        # 한 프로젝트에 repo 7개 → 5개만 analyze_repo 호출, 2개는 limit_skipped
        urls = [f"https://github.com/u/r{i}" for i in range(7)]
        projects = [{"name": "P", "tech": ["Django"], "github_urls": urls}]

        calls = []
        def side(url):
            calls.append(url)
            return _ok_repo(url, ["Django"])

        with patch(self.PATCH, side_effect=side):
            result = merge_with_github(projects)

        assert len(calls) == 5                  # 실제 분석은 5개까지만
        errors = result[0]["github_errors"]
        skipped = [e for e in errors if e["kind"] == "limit_skipped"]
        assert len(skipped) == 2                # 초과 2개는 건너뜀 기록
        assert result[0]["is_github_verified"] is True

    def test_전역_상한_여러_프로젝트_합산(self):
        # 프로젝트 A(3개) + B(4개) = 7개 → 합산 5개까지만 분석
        projects = [
            {"name": "A", "tech": ["Django"],
             "github_urls": [f"https://github.com/u/a{i}" for i in range(3)]},
            {"name": "B", "tech": ["React"],
             "github_urls": [f"https://github.com/u/b{i}" for i in range(4)]},
        ]
        calls = []
        with patch(self.PATCH, side_effect=lambda u: calls.append(u) or _ok_repo(u, [])):
            result = merge_with_github(projects)

        assert len(calls) == 5                   # A 3개 + B 2개 = 5
        b_skipped = [e for e in result[1]["github_errors"] if e["kind"] == "limit_skipped"]
        assert len(b_skipped) == 2               # B의 나머지 2개는 상한 초과


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
