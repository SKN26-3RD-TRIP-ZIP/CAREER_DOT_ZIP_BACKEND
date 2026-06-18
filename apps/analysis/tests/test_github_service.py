"""
github_service 단위 테스트

테스트 대상:
  extract_dependencies()  매니페스트 파싱 → 프레임워크 추출 (순수 함수)
  is_dependency_file()    트리 경로가 매니페스트인지 판별

실행:
  pytest apps/analysis/tests/test_github_service.py -v
"""

import pytest

from apps.analysis.services.github_service import (
    extract_dependencies,
    is_dependency_file,
    pick_key_files,
    parse_repo_url,
)


# ══════════════════════════════════════════════════════════════
# is_dependency_file
# ══════════════════════════════════════════════════════════════

class TestIsDependencyFile:

    def test_표준_매니페스트_인식(self):
        assert is_dependency_file("requirements.txt")
        assert is_dependency_file("package.json")
        assert is_dependency_file("pyproject.toml")
        assert is_dependency_file("go.mod")

    def test_하위경로_무시하고_인식(self):
        assert is_dependency_file("backend/requirements.txt")
        assert is_dependency_file("services/api/package.json")

    def test_requirements_변형_인식(self):
        assert is_dependency_file("requirements-dev.txt")
        assert is_dependency_file("requirements/base.txt")

    def test_일반_소스파일은_아님(self):
        assert not is_dependency_file("src/models.py")
        assert not is_dependency_file("README.md")


# ══════════════════════════════════════════════════════════════
# extract_dependencies — Python
# ══════════════════════════════════════════════════════════════

class TestExtractPython:

    def test_requirements_txt_프레임워크_추출(self):
        files = {
            "requirements.txt": (
                "Django==4.2.1\n"
                "djangorestframework>=3.14\n"
                "celery~=5.3\n"
                "# 주석은 무시\n"
                "-r base.txt\n"
                "psycopg2-binary==2.9\n"        # 별칭 맵에 없음 → frameworks 제외
            ),
        }
        result = extract_dependencies(files)
        assert "Django" in result["frameworks"]
        assert "Django REST Framework" in result["frameworks"]
        assert "Celery" in result["frameworks"]

    def test_미등록_패키지는_raw에만_남고_framework_제외(self):
        files = {"requirements.txt": "psycopg2-binary==2.9\n"}
        result = extract_dependencies(files)
        assert "psycopg2-binary" in result["raw_packages"]
        assert result["frameworks"] == []

    def test_pyproject_pep621_파싱(self):
        files = {
            "pyproject.toml": (
                '[project]\n'
                'dependencies = ["fastapi>=0.110", "sqlalchemy[asyncio]>=2.0"]\n'
            ),
        }
        result = extract_dependencies(files)
        assert "FastAPI" in result["frameworks"]
        assert "SQLAlchemy" in result["frameworks"]

    def test_pyproject_poetry_파싱_python은_제외(self):
        files = {
            "pyproject.toml": (
                '[tool.poetry.dependencies]\n'
                'python = "^3.13"\n'
                'flask = "^3.0"\n'
            ),
        }
        result = extract_dependencies(files)
        assert "Flask" in result["frameworks"]
        assert "python" not in result["raw_packages"]


# ══════════════════════════════════════════════════════════════
# extract_dependencies — JavaScript
# ══════════════════════════════════════════════════════════════

class TestExtractJavaScript:

    def test_package_json_dependencies_파싱(self):
        files = {
            "package.json": (
                '{"dependencies": {"react": "^18.2", "next": "14.0.0"},'
                ' "devDependencies": {"jest": "^29"}}'
            ),
        }
        result = extract_dependencies(files)
        assert "React" in result["frameworks"]
        assert "Next.js" in result["frameworks"]

    def test_스코프_패키지_매칭(self):
        files = {"package.json": '{"dependencies": {"@nestjs/core": "^10"}}'}
        result = extract_dependencies(files)
        assert "NestJS" in result["frameworks"]

    def test_깨진_json은_무시하고_빈결과(self):
        files = {"package.json": "{이건 JSON 아님"}
        result = extract_dependencies(files)
        assert result["frameworks"] == []


# ══════════════════════════════════════════════════════════════
# extract_dependencies — Go / Java (부분일치 좌표)
# ══════════════════════════════════════════════════════════════

class TestExtractCoordinateBased:

    def test_go_mod_모듈경로_부분일치(self):
        files = {
            "go.mod": (
                "module myapp\n\n"
                "go 1.22\n\n"
                "require (\n"
                "\tgithub.com/gin-gonic/gin v1.9.1\n"
                "\tgorm.io/gorm v1.25.0\n"
                ")\n"
            ),
        }
        result = extract_dependencies(files)
        assert "Gin" in result["frameworks"]
        assert "GORM" in result["frameworks"]

    def test_gradle_좌표_부분일치(self):
        files = {
            "build.gradle": (
                "dependencies {\n"
                "  implementation 'org.springframework.boot:spring-boot-starter-web'\n"
                "}\n"
            ),
        }
        result = extract_dependencies(files)
        assert "Spring Boot" in result["frameworks"]


# ══════════════════════════════════════════════════════════════
# extract_dependencies — 통합/엣지
# ══════════════════════════════════════════════════════════════

class TestExtractIntegration:

    def test_여러_repo_매니페스트_병합_및_evidence(self):
        # 프로젝트당 URL 여러 개 → backend(python) + frontend(js) 합산
        files = {
            "backend/requirements.txt": "Django==4.2\n",
            "frontend/package.json":    '{"dependencies": {"react": "^18"}}',
        }
        result = extract_dependencies(files)
        assert "Django" in result["frameworks"]
        assert "React" in result["frameworks"]
        # evidence가 근거 파일을 가리켜야 함 (Reconcile basis용)
        assert result["evidence"]["Django"] == ["backend/requirements.txt"]

    def test_의존성_파일_아닌건_무시(self):
        files = {"src/models.py": "import django", "README.md": "# Django 씀"}
        result = extract_dependencies(files)
        assert result["frameworks"] == []        # 본문 텍스트는 신뢰하지 않음

    def test_빈_입력(self):
        result = extract_dependencies({})
        assert result == {"frameworks": [], "raw_packages": [], "evidence": {}}

    def test_프레임워크_정렬_및_중복제거(self):
        files = {
            "requirements.txt": "django\n",
            "backend/requirements.txt": "django\nfastapi\n",
        }
        result = extract_dependencies(files)
        assert result["frameworks"] == sorted(result["frameworks"])
        assert result["frameworks"].count("Django") == 1


# ══════════════════════════════════════════════════════════════
# parse_repo_url
# ══════════════════════════════════════════════════════════════

class TestParseRepoUrl:

    def test_표준_url(self):
        assert parse_repo_url("https://github.com/o/r") == ("o", "r")

    def test_git_suffix(self):
        assert parse_repo_url("https://github.com/o/r.git") == ("o", "r")

    def test_deep_link(self):
        assert parse_repo_url("https://github.com/o/r/tree/main") == ("o", "r")

    def test_github_아니면_거부(self):
        import pytest
        with pytest.raises(ValueError):
            parse_repo_url("https://gitlab.com/o/r")
        with pytest.raises(ValueError):
            parse_repo_url("그냥 텍스트")


# ══════════════════════════════════════════════════════════════
# pick_key_files — 코드 심화 질문용 핵심 파일 선별
# ══════════════════════════════════════════════════════════════

class TestPickKeyFiles:

    def test_핵심_소스_우선_선별(self):
        tree = [
            "README.md", "src/models.py", "src/views.py",
            "tests/test_x.py", "Dockerfile", "assets/logo.png",
        ]
        picked = pick_key_files(tree, limit=4)
        assert "src/models.py" in picked
        assert "Dockerfile" in picked
        assert "assets/logo.png" not in picked     # 코드 아님
        assert "README.md" not in picked           # 매니페스트/문서는 별도 단계

    def test_limit_준수(self):
        tree = [f"app/service_{i}.py" for i in range(10)]
        assert len(pick_key_files(tree, limit=3)) == 3

    def test_루트_가까운_경로_우선(self):
        tree = ["a/b/c/d/models.py", "models.py"]
        picked = pick_key_files(tree, limit=1)
        assert picked == ["models.py"]              # 더 얕은 경로 우선


# ══════════════════════════════════════════════════════════════
# analyze_repo — 예외처리 (requests.get 모킹, 네트워크 없음)
#   ★ 핵심: 어떤 실패든 예외를 던지지 않고 ok=False로 흡수하는지 검증
# ══════════════════════════════════════════════════════════════

import os
import base64
from unittest.mock import patch
from apps.analysis.services import github_service as gh


class _FakeResp:
    def __init__(self, code, payload=None, headers=None):
        self.status_code = code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def _github_router(scenario: str):
    """repo 분석에 필요한 GitHub 엔드포인트들을 가짜로 라우팅하는 get 함수를 만든다."""
    def fake_get(url, headers=None, timeout=None, params=None, **kwargs):
        if scenario == "network":
            raise gh.requests.ConnectionError("boom")
        if scenario == "timeout":
            raise gh.requests.Timeout("slow")

        if "/git/trees/" in url:
            return _FakeResp(200, {"tree": [
                {"path": "requirements.txt", "type": "blob"},
                {"path": "src/models.py",    "type": "blob"},
            ]})
        if url.endswith("/languages"):
            return _FakeResp(200, {"Python": 1000})
        if "/contents/" in url:
            content = base64.b64encode(b"Django==4.2\ncelery\n").decode()
            return _FakeResp(200, {"encoding": "base64", "content": content})

        # repo 메타 (base) — 시나리오별 분기 지점
        if scenario == "not_found":
            return _FakeResp(404)
        if scenario == "rate_limit":
            return _FakeResp(403, headers={"X-RateLimit-Remaining": "0"})
        if scenario == "auth":
            return _FakeResp(401, headers={"X-RateLimit-Remaining": "10"})
        return _FakeResp(200, {"default_branch": "main"})
    return fake_get


class TestAnalyzeRepoExceptions:

    def _run(self, scenario, url="https://github.com/u/r"):
        with patch.object(gh.requests, "get", _github_router(scenario)):
            return gh.analyze_repo(url)

    def test_성공_경로(self):
        r = self._run("success")
        assert r["ok"] is True
        assert "Django" in r["frameworks"]
        assert "Celery" in r["frameworks"]
        assert r["languages"] == {"Python": 1000}
        assert r["error"] is None

    def test_잘못된_url은_호출도_안함(self):
        # patch 없이도 네트워크 안 탐 (parse 단계에서 거름)
        r = gh.analyze_repo("https://gitlab.com/u/r")
        assert r["ok"] is False and r["error_kind"] == "invalid_url"

    def test_404는_not_found(self):
        r = self._run("not_found")
        assert r["ok"] is False and r["error_kind"] == "not_found"

    def test_rate_limit_구분(self):
        r = self._run("rate_limit")
        assert r["error_kind"] == "rate_limit"

    def test_인증실패는_auth(self):
        r = self._run("auth")
        assert r["error_kind"] == "auth"

    def test_네트워크_예외도_안던짐(self):
        r = self._run("network")               # 예외 없이 끝나야 함
        assert r["ok"] is False and r["error_kind"] == "network"

    def test_타임아웃도_network로_흡수(self):
        r = self._run("timeout")
        assert r["error_kind"] == "network"

    def test_어떤_시나리오도_예외_안던짐(self):
        # 모든 실패 종류를 돌려도 raise 없이 dict 반환
        for scn in ["success", "not_found", "rate_limit", "auth", "network", "timeout"]:
            r = self._run(scn)
            assert isinstance(r, dict) and "ok" in r


# ══════════════════════════════════════════════════════════════
# 통합 테스트 — 실제 GitHub API (마커 격리, 토큰 있을 때만)
#   실행: pytest -m integration
#   제외: pytest -m "not integration"   (CI 기본)
# ══════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GITHUB_TOKEN"), reason="GITHUB_TOKEN 필요")
class TestAnalyzeRepoIntegration:

    def test_실제_공개_repo_분석(self):
        from apps.analysis.services.github_service import analyze_repo
        r = analyze_repo("https://github.com/pallets/flask")
        assert r["ok"] is True
        # 언어 또는 프레임워크 중 하나로 Python/Flask가 잡혀야 함
        assert "Python" in r["languages"] or "Flask" in r["frameworks"]
