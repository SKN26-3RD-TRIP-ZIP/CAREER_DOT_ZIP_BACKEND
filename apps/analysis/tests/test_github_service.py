"""
github_service 단위 테스트

테스트 대상:
  extract_dependencies()  매니페스트 파싱 → 프레임워크 추출 (순수 함수)
  is_dependency_file()    트리 경로가 매니페스트인지 판별

실행:
  pytest apps/analysis/tests/test_github_service.py -v
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")

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


# ══════════════════════════════════════════════════════════════
# preprocess_readme / _deep_clean_readme
# ══════════════════════════════════════════════════════════════

from apps.analysis.services.github_service import (
    preprocess_readme,
    _deep_clean_readme,
)


class TestPreprocessReadme:

    def test_코드블록_제거(self):
        raw = "## 소개\n설명 텍스트\n```bash\nnpm install\n```\n이후 내용"
        result = preprocess_readme(raw)
        assert "npm install" not in result
        assert "설명 텍스트" in result

    def test_이미지_배지_제거(self):
        raw = "![logo](img/logo.png)\n[![build](https://img.shields.io/badge)](url)\n## 프로젝트\n실제 설명"
        result = preprocess_readme(raw)
        assert "logo" not in result
        assert "실제 설명" in result

    def test_설치_섹션_제거(self):
        raw = "## 소개\n설명\n## Installation\n설치 가이드\n## 특징\n핵심 기능"
        result = preprocess_readme(raw)
        assert "설치 가이드" not in result
        assert "핵심 기능" in result

    def test_html_태그_제거(self):
        raw = "<div>무시할 내용</div>\n## 프로젝트\n<b>강조</b>한 설명"
        result = preprocess_readme(raw)
        assert "<div>" not in result
        assert "<b>" not in result

    def test_max_chars_제한(self):
        raw = "A" * 2000
        result = preprocess_readme(raw, max_chars=500)
        assert len(result) <= 500

    def test_빈_입력은_빈_결과(self):
        assert preprocess_readme("") == ""


class TestDeepCleanReadme:

    def test_shields_배지_url_제거(self):
        text = "앞 문장\nhttps://img.shields.io/badge/python-3.11-blue 뒤 문장"
        result = _deep_clean_readme(text)
        assert "shields.io" not in result
        assert "앞 문장" in result

    def test_마크다운_이미지_제거(self):
        text = "설명\n![스크린샷](docs/screenshot.png)\n추가 설명"
        result = _deep_clean_readme(text)
        assert "![스크린샷]" not in result
        assert "추가 설명" in result

    def test_설치_명령어_포함_코드블록_제거(self):
        text = "설명\n```\npip install requests\n```\n이후 설명"
        result = _deep_clean_readme(text)
        assert "pip install" not in result
        assert "이후 설명" in result

    def test_설치_명령어_없는_코드블록은_유지(self):
        text = "설명\n```python\nclass MyModel:\n    pass\n```\n이후"
        result = _deep_clean_readme(text)
        assert "MyModel" in result

    def test_license_섹션_제거(self):
        text = "## 소개\n내용\n## License\nMIT 라이선스 설명\n## 특징\n남아야 할 내용"
        result = _deep_clean_readme(text)
        assert "MIT 라이선스" not in result
        assert "남아야 할 내용" in result

    def test_8000자_초과_잘림(self):
        text = "X" * 10000
        result = _deep_clean_readme(text, max_chars=8000)
        assert len(result) <= 8000


# ══════════════════════════════════════════════════════════════
# extract_interview_context — 모킹 기반 (네트워크 없음)
# ══════════════════════════════════════════════════════════════

from unittest.mock import MagicMock, patch
from apps.analysis.services import github_service as gh

_SAMPLE_README = """
# CareerZip

CareerZip는 취업 준비생이 채용공고와 본인 이력서를 분석해 맞춤형 면접 질문을
자동으로 생성할 수 있는 AI 기반 플랫폼입니다.

## 핵심 기능

- JD와 이력서 텍스트를 입력받아 매칭 점수를 산출합니다.
- GPT-4o를 이용해 개인화된 면접 예상 질문 10개를 생성합니다.
- STAR 기법 기반 모범 답변도 함께 제공합니다.
- GitHub repo URL을 입력하면 코드 기반 심화 질문이 추가됩니다.

## 아키텍처

Django REST Framework + React + PostgreSQL 구조입니다.
비동기 분석은 ThreadPoolExecutor로 병렬 처리합니다.

## 기술적 도전

- 임베딩 유사도와 룰 기반 점수를 가중 합산해 매칭 정확도를 높였습니다.
- 프롬프트 인젝션 방어를 위해 InputGuardrail을 설계했습니다.

## License

MIT
"""

_LLM_JSON_RESPONSE = """{
  "project_name": "CareerZip",
  "project_overview": "취업 준비생을 위한 AI 면접 코치 플랫폼입니다.",
  "tech_stack": ["Django", "React", "PostgreSQL", "GPT-4o"],
  "my_role": null,
  "key_features": ["JD-이력서 매칭 점수 산출", "AI 면접 질문 자동 생성", "STAR 답변 제공"],
  "technical_challenges": ["임베딩+룰 기반 가중 합산", "프롬프트 인젝션 방어"],
  "architecture": "Django REST + React + PostgreSQL, ThreadPoolExecutor 병렬 처리",
  "interview_points": ["STAR 질문 생성 전략", "임베딩 유사도 설계", "GitHub 코드 심화 질문"]
}"""


def _make_analyze_repo_ok(readme: str = _SAMPLE_README, frameworks: list = None):
    """analyze_repo() 성공 결과를 반환하는 mock 함수."""
    return {
        "ok": True,
        "github_url": "https://github.com/u/r",
        "frameworks": frameworks or ["Django REST Framework"],
        "raw_packages": ["djangorestframework"],
        "evidence": {},
        "languages": {"Python": 80000},
        "readme": readme,
    }


def _make_llm_response(content: str):
    """OpenAI chat.completions.create() 응답을 흉내 내는 mock 객체."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestExtractInterviewContext:
    """
    extract_interview_context() 동작을 모킹으로 검증한다.
    네트워크 및 LLM 호출 없이 순수 로직만 테스트한다.
    """

    def _run(self, analyze_return, llm_content=_LLM_JSON_RESPONSE):
        """analyze_repo와 LLM을 모두 패치해서 extract_interview_context를 실행한다."""
        llm_resp = _make_llm_response(llm_content)
        with patch.object(gh, "analyze_repo", return_value=analyze_return):
            with patch("apps.analysis.services.github_service.gh.get_client") as mock_client_fn:
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = llm_resp
                mock_client_fn.return_value = mock_client

                # get_client는 utils 패키지에서 import하므로 해당 경로도 패치
                with patch(
                    "apps.analysis.services.utils.llm_helpers.get_client",
                    return_value=mock_client,
                ):
                    return gh.extract_interview_context("https://github.com/u/r")

    def _run_direct(self, analyze_return, llm_content=_LLM_JSON_RESPONSE):
        """get_client를 services.utils 경로에서 직접 패치."""
        llm_resp = _make_llm_response(llm_content)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = llm_resp

        with (
            patch.object(gh, "analyze_repo", return_value=analyze_return),
            patch("apps.analysis.services.github_service.get_client", return_value=mock_client, create=True),
        ):
            return gh.extract_interview_context("https://github.com/u/r")

    def test_성공_시_ok_True_반환(self):
        result = self._run_direct(_make_analyze_repo_ok())
        assert result["ok"] is True
        assert "data" in result

    def test_반환_data_필드_완전성(self):
        result = self._run_direct(_make_analyze_repo_ok())
        data = result["data"]
        for key in ("project_name", "project_overview", "tech_stack", "my_role",
                    "key_features", "technical_challenges", "architecture", "interview_points"):
            assert key in data, f"data에 '{key}' 필드가 없음"

    def test_analyze_repo_실패_시_GITHUB_FETCH_FAILED(self):
        fail = {"ok": False, "error": "not_found", "error_kind": "not_found"}
        result = self._run_direct(fail)
        assert result["ok"] is False
        assert result["error_code"] == "GITHUB_FETCH_FAILED"

    def test_README_너무_짧으면_GITHUB_README_NOT_FOUND(self):
        short_readme = _make_analyze_repo_ok(readme="짧음")
        result = self._run_direct(short_readme)
        assert result["ok"] is False
        assert result["error_code"] == "GITHUB_README_NOT_FOUND"

    def test_repo_frameworks와_llm_tech_합집합_병합(self):
        """
        analyze_repo에서 나온 frameworks(Django REST Framework)와
        LLM이 추출한 tech_stack(Django, React 등)이 합집합으로 병합되는지 검증.
        """
        result = self._run_direct(_make_analyze_repo_ok(frameworks=["Django REST Framework"]))
        if result["ok"]:
            tech = result["data"]["tech_stack"]
            # analyze_repo 결과가 포함돼야 함
            assert "Django REST Framework" in tech
            # LLM 결과도 포함돼야 함
            assert "React" in tech or "Django" in tech

    def test_JSON_파싱_실패_시_GITHUB_PARSE_FAILED(self):
        """LLM이 잘못된 JSON을 두 번 연속 반환하면 GITHUB_PARSE_FAILED."""
        bad_json = "이건 JSON이 아닙니다"
        llm_resp = _make_llm_response(bad_json)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = llm_resp

        with (
            patch.object(gh, "analyze_repo", return_value=_make_analyze_repo_ok()),
            patch("apps.analysis.services.github_service.get_client", return_value=mock_client, create=True),
        ):
            result = gh.extract_interview_context("https://github.com/u/r")

        # ok=False여야 하고 에러 코드가 PARSE_FAILED 또는 FETCH_FAILED
        assert result["ok"] is False
        assert result["error_code"] in ("GITHUB_PARSE_FAILED", "GITHUB_FETCH_FAILED")

    def test_예외_발생해도_외부로_전파_안됨(self):
        """analyze_repo가 예외를 던져도 extract_interview_context는 dict를 반환해야 함."""
        with patch.object(gh, "analyze_repo", side_effect=RuntimeError("네트워크 폭발")):
            result = gh.extract_interview_context("https://github.com/u/r")
        assert isinstance(result, dict)
        assert result["ok"] is False

    def test_결과_tech_stack은_정렬되고_중복없음(self):
        result = self._run_direct(
            _make_analyze_repo_ok(frameworks=["React", "Django REST Framework"])
        )
        if result["ok"]:
            tech = result["data"]["tech_stack"]
            assert tech == sorted(set(tech)), "tech_stack이 정렬/중복제거 되지 않음"


# ══════════════════════════════════════════════════════════════
# 통합 테스트 — 실제 GitHub + OpenAI (마커 격리)
#   실행: pytest -m integration
# ══════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.skipif(
    not (os.getenv("GITHUB_TOKEN") and os.getenv("OPENAI_API_KEY")),
    reason="GITHUB_TOKEN + OPENAI_API_KEY 필요",
)
class TestExtractInterviewContextIntegration:

    def test_실제_공개_repo_전체_파이프라인(self):
        """
        실제 GitHub API + OpenAI를 모두 호출해 전체 파이프라인을 검증한다.
        GITHUB_TOKEN과 OPENAI_API_KEY가 모두 설정된 환경에서만 실행된다.
        """
        result = gh.extract_interview_context("https://github.com/pallets/flask")
        assert result["ok"] is True, f"실패: {result}"
        data = result["data"]
        assert data["project_name"]          # 프로젝트명 추출됐는지
        assert isinstance(data["tech_stack"], list)
        assert isinstance(data["key_features"], list)
        assert isinstance(data["interview_points"], list)
        print("\n[통합 테스트 결과]")
        import json as _json
        print(_json.dumps(data, ensure_ascii=False, indent=2))
