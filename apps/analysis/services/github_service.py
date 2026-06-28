"""
Pipeline 1 - ② GitHub 연동 / 의존성 추출 (Layer 1)

역할:
  repo의 의존성 매니페스트 파일(requirements.txt, package.json 등)을 파싱해
  실제로 사용한 프레임워크 목록을 추출한다.
  언어 통계(/languages)가 잡지 못하는 Django·React 같은 프레임워크를
  결정적으로(LLM 없이) 검증하기 위한 단계.

  project_service.merge_with_github()의 Reconcile 단계에서
  이력서 tech 주장과 대조하는 데 사용된다.

포함:
  FRAMEWORK_ALIASES      패키지명 → 이력서 정식 명칭 매핑 테이블
  DEPENDENCY_FILENAMES   Fetch 단계에서 우선 수집할 매니페스트 파일명
  is_dependency_file()   트리 경로가 매니페스트 파일인지 판별
  extract_dependencies() {경로: 내용} → 프레임워크/패키지 목록 (순수 함수, I/O 없음)
"""

import os
import re
import json
import base64
import tomllib
import logging

import requests

from .analysis_prompt import build_interview_context_prompt

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 별칭 맵: 패키지명(소문자) → 이력서에서 쓰는 정식 명칭
#   - python/js: 패키지명 정확히 일치로 매칭
#   - go/java:   "/" 또는 "-starter" 포함 키는 전체 좌표 부분일치로 매칭
#   프로젝트에서 자주 나오는 스택 위주로 계속 추가하세요.
# ══════════════════════════════════════════════════════════════
FRAMEWORK_ALIASES: dict[str, str] = {
    # ── Python (web/backend) ──
    "django":              "Django",
    "djangorestframework": "Django REST Framework",
    "fastapi":             "FastAPI",
    "flask":               "Flask",
    "starlette":           "Starlette",
    "celery":              "Celery",
    "sqlalchemy":          "SQLAlchemy",
    "pydantic":            "Pydantic",
    "gunicorn":            "Gunicorn",
    "uvicorn":             "Uvicorn",
    "scrapy":              "Scrapy",
    # ── Python (data/ML) ──
    "torch":               "PyTorch",
    "tensorflow":          "TensorFlow",
    "keras":               "Keras",
    "scikit-learn":        "scikit-learn",
    "sklearn":             "scikit-learn",
    "pandas":              "pandas",
    "numpy":               "NumPy",
    "transformers":        "Hugging Face Transformers",
    "langchain":           "LangChain",
    "openai":              "OpenAI SDK",
    # ── JavaScript / TypeScript ──
    "react":               "React",
    "react-dom":           "React",
    "next":                "Next.js",
    "vue":                 "Vue.js",
    "nuxt":                "Nuxt",
    "@angular/core":       "Angular",
    "svelte":              "Svelte",
    "express":             "Express",
    "@nestjs/core":        "NestJS",
    "koa":                 "Koa",
    "fastify":             "Fastify",
    "socket.io":           "Socket.IO",
    "prisma":              "Prisma",
    "typeorm":             "TypeORM",
    "redux":               "Redux",
    "@reduxjs/toolkit":    "Redux Toolkit",
    "axios":               "Axios",
    "tailwindcss":         "Tailwind CSS",
    # ── Java / Kotlin (전체 좌표 부분일치) ──
    "spring-boot-starter": "Spring Boot",
    "spring-webmvc":       "Spring MVC",
    "spring-security":     "Spring Security",
    "hibernate-core":      "Hibernate",
    "mybatis":             "MyBatis",
    # ── Go (모듈 경로 부분일치) ──
    "gin-gonic/gin":       "Gin",
    "labstack/echo":       "Echo",
    "gofiber/fiber":       "Fiber",
    "gorm.io/gorm":        "GORM",
    # ── Ruby ──
    "rails":               "Ruby on Rails",
    "sinatra":             "Sinatra",
}

# 부분일치(전체 좌표)로 매칭할 별칭 키 — go 모듈 경로, java artifactId 등
_SUBSTRING_KEYS = [k for k in FRAMEWORK_ALIASES if "/" in k or k.endswith("-starter")]


# ══════════════════════════════════════════════════════════════
# 매니페스트 파일 식별 — Fetch 단계가 어떤 파일을 가져올지 결정
# ══════════════════════════════════════════════════════════════
DEPENDENCY_FILENAMES = {
    "requirements.txt", "pyproject.toml", "pipfile",
    "package.json",
    "go.mod",
    "gemfile",
    "pom.xml", "build.gradle", "build.gradle.kts",
}

README_FILENAMES = {"readme.md", "readme.rst", "readme.txt", "readme"}


def _path_parts(path: str) -> list[str]:
    return [part for part in str(path or "").replace("\\", "/").lower().split("/") if part]


def _is_requirements_file(path: str) -> bool:
    parts = _path_parts(path)
    if not parts:
        return False
    name = parts[-1]
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return name.endswith(".txt") and "requirements" in parts[:-1]


def is_dependency_file(path: str) -> bool:
    """트리 경로가 의존성 매니페스트인지 판별. (대소문자·하위 경로 무시)"""
    parts = _path_parts(path)
    name = parts[-1] if parts else ""
    if name in DEPENDENCY_FILENAMES:
        return True
    # requirements-dev.txt, requirements/base.txt 등 변형 허용
    return _is_requirements_file(path)


def is_readme_file(path: str) -> bool:
    """루트 레벨 README 파일인지 판별. 하위 디렉터리의 README는 제외."""
    if "/" in path:
        return False
    return os.path.basename(path).lower() in README_FILENAMES


# ══════════════════════════════════════════════════════════════
# 매니페스트별 파서 — 각자 "패키지명 후보 토큰" 리스트를 반환
#   python/js : 베어 패키지명 (예: "django")
#   go/java   : 전체 좌표      (예: "github.com/gin-gonic/gin")
# 어떤 파서든 파싱 실패 시 [] 반환 (전체 분석을 죽이지 않는다)
# ══════════════════════════════════════════════════════════════

def _pkg_name(spec: str) -> str:
    """'django>=4.2 ; python_version>"3"' → 'django' (버전·extras·마커 제거, 소문자)"""
    spec = spec.strip().split(";")[0].strip()        # 환경 마커 제거
    # 첫 버전/extras 구분자 앞까지가 이름
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", " ", "@"):
        idx = spec.find(sep)
        if idx != -1:
            spec = spec[:idx]
    return spec.strip().lower()


def _parse_requirements_txt(content: str) -> list[str]:
    names = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue                                  # 주석, -r/-e/--옵션 스킵
        if "://" in line:
            continue                                  # 직접 URL 의존성 스킵
        name = _pkg_name(line)
        if name:
            names.append(name)
    return names


def _parse_pyproject(content: str) -> list[str]:
    try:
        data = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    names = []
    # PEP 621: [project] dependencies = ["django>=4.2", ...]
    for spec in data.get("project", {}).get("dependencies", []) or []:
        names.append(_pkg_name(spec))
    # optional-dependencies: {group: [..]}
    for group in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
        names += [_pkg_name(s) for s in group]
    # Poetry: [tool.poetry.dependencies] = {django = "^4.2", python = "^3.13"}
    poetry = data.get("tool", {}).get("poetry", {})
    for key in ("dependencies", "dev-dependencies"):
        for name in (poetry.get(key, {}) or {}):
            if name.lower() != "python":
                names.append(name.lower())
    return [n for n in names if n]


def _parse_pipfile(content: str) -> list[str]:
    try:
        data = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    names = []
    for section in ("packages", "dev-packages"):
        for name in (data.get(section, {}) or {}):
            names.append(name.lower())
    return names


def _parse_package_json(content: str) -> list[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []
    names = []
    for section in ("dependencies", "devDependencies"):
        for name in (data.get(section, {}) or {}):
            names.append(name.lower())               # 스코프(@nestjs/core)는 그대로 유지
    return names


def _parse_gemfile(content: str) -> list[str]:
    import re
    return [m.lower() for m in re.findall(r"""gem\s+['"]([\w.-]+)['"]""", content)]


def _parse_go_mod(content: str) -> list[str]:
    """require 블록/단일 require에서 모듈 전체 경로를 뽑는다."""
    import re
    paths = []
    for line in content.splitlines():
        line = line.strip().removeprefix("require ").strip()
        m = re.match(r"([\w./-]+)\s+v[\d.]", line)   # 'github.com/x/y v1.2.3'
        if m:
            paths.append(m.group(1).lower())
    return paths


def _parse_maven_gradle(content: str) -> list[str]:
    """pom.xml의 <artifactId> / gradle의 'group:artifact:ver' 좌표를 뽑는다."""
    import re
    tokens = re.findall(r"<artifactId>([\w.-]+)</artifactId>", content)        # pom
    tokens += re.findall(r"""['"][\w.-]+:([\w.-]+)(?::[\w.${}-]+)?['"]""", content)  # gradle
    return [t.lower() for t in tokens]


def _parser_for(path: str):
    parts = _path_parts(path)
    name = parts[-1] if parts else ""
    if _is_requirements_file(path):
        return _parse_requirements_txt
    return {
        "pyproject.toml":    _parse_pyproject,
        "pipfile":           _parse_pipfile,
        "package.json":      _parse_package_json,
        "gemfile":           _parse_gemfile,
        "go.mod":            _parse_go_mod,
        "pom.xml":           _parse_maven_gradle,
        "build.gradle":      _parse_maven_gradle,
        "build.gradle.kts":  _parse_maven_gradle,
    }.get(name)


def _to_frameworks(tokens: list[str]) -> list[str]:
    """패키지명 토큰 → 별칭 맵으로 정식 프레임워크 명칭 변환."""
    found = []
    for tok in tokens:
        if tok in FRAMEWORK_ALIASES:                 # 정확 일치 (python/js)
            found.append(FRAMEWORK_ALIASES[tok])
            continue
        for key in _SUBSTRING_KEYS:                  # 부분 일치 (go/java 좌표)
            if key in tok:
                found.append(FRAMEWORK_ALIASES[key])
                break
    return found


# ══════════════════════════════════════════════════════════════
# 공개 진입점
# ══════════════════════════════════════════════════════════════

def extract_dependencies(files: dict[str, str]) -> dict:
    """
    매니페스트 파일들을 파싱해 사용 프레임워크를 추출한다. (순수 함수, 네트워크 호출 없음)

    Args:
        files: {파일경로: 파일내용} — Fetch 단계에서 받은 매니페스트들.
               의존성 파일이 아닌 항목이 섞여 있어도 무시한다.

    Returns:
        {
            "frameworks":   ["Django", "Django REST Framework", "Celery"],  # 정식 명칭, 정렬·중복제거
            "raw_packages": ["celery", "django", "djangorestframework"],    # 원본 패키지명 (투명성용)
            "evidence":     {"Django": ["requirements.txt"]},               # 프레임워크별 근거 파일
        }

    이력서 tech 주장과 frameworks를 대조하면 verified / unverified가 갈린다.
    """
    raw_packages: set[str] = set()
    frameworks: set[str] = set()
    evidence: dict[str, list[str]] = {}

    for path, content in files.items():
        parser = _parser_for(path)
        if parser is None or not content:
            continue

        tokens = parser(content)
        raw_packages.update(tokens)

        for fw in _to_frameworks(tokens):
            frameworks.add(fw)
            evidence.setdefault(fw, [])
            if path not in evidence[fw]:
                evidence[fw].append(path)

    return {
        "frameworks":   sorted(frameworks),
        "raw_packages": sorted(raw_packages),
        "evidence":     evidence,
    }


# ══════════════════════════════════════════════════════════════
# Fetch 단계 — GitHub REST API 호출 (I/O, 예외 발생 가능)
#
# 설계 원칙: 모든 실패를 _RepoError로 정규화하고, analyze_repo()가
# 이를 잡아 "사용자 친화 메시지를 담은 결과 dict"로 변환한다.
# → 외부로 예외를 던지지 않으므로 repo 하나가 죽어도 전체 분석은 계속된다.
# ══════════════════════════════════════════════════════════════

GITHUB_API = "https://api.github.com"
_TIMEOUT = 10
_MAX_MANIFESTS = 20          # 한 repo에서 가져올 매니페스트 상한 (모노레포 폭주 방지)


class _RepoError(Exception):
    """repo 수집 실패. kind로 실패 종류를 구분해 호출부가 분기할 수 있게 한다."""
    def __init__(self, message: str, *, kind: str):
        super().__init__(message)
        self.message = message
        # "invalid_url" | "not_found" | "rate_limit" | "auth" | "network" | "unknown"
        self.kind = kind


def parse_repo_url(url: str) -> tuple[str, str]:
    """
    https://github.com/owner/repo(.git)?(/tree/main 등)? → (owner, repo)
    github.com 도메인만 허용한다 (SSRF 방지). 형식이 아니면 ValueError.
    """
    m = re.search(
        r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git|/.*)?/?$",
        (url or "").strip(),
    )
    if not m:
        raise ValueError(f"GitHub repo URL이 아님: {url!r}")
    return m.group(1), m.group(2)


def _headers() -> dict:
    # 환경변수 우선, 없으면 settings 폴백 (settings 미구성 환경에서도 안전)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            from django.conf import settings
            token = getattr(settings, "GITHUB_TOKEN", "") or ""
        except Exception:
            token = ""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(path: str, **kwargs) -> requests.Response:
    """GET 요청. 네트워크 계층 실패를 _RepoError(network)로 정규화."""
    try:
        return requests.get(
            f"{GITHUB_API}{path}", headers=_headers(), timeout=_TIMEOUT, **kwargs
        )
    except requests.Timeout:
        raise _RepoError("GitHub 응답 시간이 초과되었습니다.", kind="network")
    except requests.RequestException:
        raise _RepoError("GitHub에 연결할 수 없습니다.", kind="network")


def _check(res: requests.Response) -> requests.Response:
    """HTTP 상태코드를 사용자 친화 _RepoError로 변환. 200대면 그대로 통과."""
    if res.status_code < 400:
        return res
    if res.status_code == 404:
        raise _RepoError("repo를 찾을 수 없습니다 (비공개·삭제·URL 오타).", kind="not_found")
    if res.status_code in (401, 403):
        if res.headers.get("X-RateLimit-Remaining") == "0":
            raise _RepoError(
                "GitHub API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
                kind="rate_limit",
            )
        raise _RepoError("GitHub 인증에 실패했습니다 (토큰 확인 필요).", kind="auth")
    raise _RepoError(f"GitHub 오류 (HTTP {res.status_code}).", kind="network")


def fetch_file(owner: str, repo: str, path: str) -> str:
    """단일 파일 내용(텍스트)을 반환. 실패하면 빈 문자열 (개별 파일 실패는 치명적이지 않음)."""
    try:
        res = _get(f"/repos/{owner}/{repo}/contents/{path}")
    except _RepoError:
        return ""
    if res.status_code != 200:
        return ""
    data = res.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")
    return ""


def fetch_manifests(owner: str, repo: str) -> dict:
    """
    repo 메타·언어통계·매니페스트 파일 내용을 수집한다.
    실패 시 _RepoError를 던진다 (analyze_repo가 잡는다).
    """
    base = f"/repos/{owner}/{repo}"
    meta = _check(_get(base)).json()
    branch = meta.get("default_branch", "main")

    # 언어통계 (base 언어 검증용) — 실패해도 빈 dict로 진행
    try:
        languages = _check(_get(f"{base}/languages")).json()
    except _RepoError:
        languages = {}

    # 파일 트리에서 매니페스트만 선별
    tree = _check(
        _get(f"{base}/git/trees/{branch}", params={"recursive": "1"})
    ).json()
    manifest_paths = [
        t["path"]
        for t in tree.get("tree", [])
        if t.get("type") == "blob" and is_dependency_file(t["path"])
    ][:_MAX_MANIFESTS]

    files = {}
    for path in manifest_paths:
        content = fetch_file(owner, repo, path)
        if content:
            files[path] = content

    # 루트 README 수집 (프로젝트 도메인/목적 파악용)
    readme_content = ""
    for t in tree.get("tree", []):
        if t.get("type") == "blob" and is_readme_file(t["path"]):
            raw = fetch_file(owner, repo, t["path"])
            readme_content = preprocess_readme(raw) if raw else ""
            break

    return {"default_branch": branch, "languages": languages, "files": files, "readme": readme_content}


def analyze_repo(url: str) -> dict:
    """
    repo URL 하나를 분석해 프레임워크/언어 정보를 반환한다.
    ★ 절대 예외를 던지지 않는다 — 모든 실패는 ok=False + error 메시지로 표현.

    반환:
    {
        "github_url": url,
        "ok":         True/False,        # 연결·분석 성공 여부
        "error":      None | "메시지",   # 실패 시 사용자 친화 설명
        "error_kind": None | "not_found" | "rate_limit" | "auth" | "network" | "invalid_url" | "unknown",
        "frameworks":   ["Django", ...], # 성공 시
        "raw_packages": [...],
        "evidence":     {...},
        "languages":    {"Python": 18234, ...},
    }
    """
    result = {
        "github_url": url, "ok": False, "error": None, "error_kind": None,
        "frameworks": [], "raw_packages": [], "evidence": {}, "languages": {},
    }

    try:
        owner, repo = parse_repo_url(url)
    except ValueError:
        result["error"] = "올바른 GitHub repo URL이 아닙니다."
        result["error_kind"] = "invalid_url"
        return result

    try:
        data = fetch_manifests(owner, repo)
    except _RepoError as e:
        result["error"] = e.message
        result["error_kind"] = e.kind
        return result
    except Exception:
        # 예상치 못한 오류(JSON 파싱 등)도 전체 분석을 죽이지 않는다
        result["error"] = "GitHub 분석 중 알 수 없는 오류가 발생했습니다."
        result["error_kind"] = "unknown"
        return result

    deps = extract_dependencies(data["files"])
    result.update(
        ok=True, owner=owner, repo=repo,
        frameworks=deps["frameworks"], raw_packages=deps["raw_packages"],
        evidence=deps["evidence"], languages=data["languages"],
        default_branch=data["default_branch"],
        readme=data.get("readme", ""),
    )
    return result


# ══════════════════════════════════════════════════════════════
# README 전처리 — 노이즈 제거 후 도메인 설명 텍스트만 남긴다
# ══════════════════════════════════════════════════════════════

# 설치·기여·라이선스 등 도메인 설명과 무관한 섹션 제목 패턴
_SKIP_SECTIONS = re.compile(
    r"^#{1,3}\s*(install|setup|getting started|usage|how to run|quickstart|"
    r"contributing|contributors|license|changelog|faq|troubleshooting|"
    r"contact|acknowledgement|credit|설치|시작|사용법|기여|라이선스|변경이력)",
    re.IGNORECASE,
)


def preprocess_readme(raw: str, max_chars: int = 1000) -> str:
    """
    README 원문에서 노이즈를 제거하고 프로젝트 도메인/목적 설명 텍스트만 남긴다.
    (순수 함수, 네트워크 없음)

    제거 대상:
      - 뱃지: [![...](...)](#)
      - 이미지: ![...](...)
      - 코드블록: ```...```
      - 인라인 코드: `...`
      - HTML 태그
      - 설치·라이선스 등 무관 섹션 전체
    """
    lines = raw.splitlines()
    result: list[str] = []
    skip_section = False
    in_code_block = False

    for line in lines:
        # 코드블록 토글
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # 섹션 제목 감지
        if re.match(r"^#{1,3}\s+", line):
            skip_section = bool(_SKIP_SECTIONS.match(line))
            if not skip_section:
                result.append(re.sub(r"^#{1,3}\s+", "", line).strip())
            continue

        if skip_section:
            continue

        # 노이즈 제거
        line = re.sub(r"!\[.*?\]\(.*?\)", "", line)          # 이미지
        line = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", line)  # 뱃지
        line = re.sub(r"<[^>]+>", "", line)                   # HTML 태그
        line = re.sub(r"`[^`]+`", "", line)                   # 인라인 코드
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # 링크 → 텍스트만
        line = line.strip()

        if line:
            result.append(line)

    cleaned = "\n".join(result).strip()
    # 연속 빈줄 정리
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned[:max_chars]


# ══════════════════════════════════════════════════════════════
# 코드 스니펫 수집 — "코드 심화 질문"용 (질문 생성 단계에서만 호출)
#   아키텍처가 드러나는 핵심 소스 파일만 골라 일부만 가져온다 (토큰 예산).
# ══════════════════════════════════════════════════════════════

_KEY_FILE_HINTS = (
    "models", "main", "app", "settings", "views", "urls", "schema",
    "router", "server", "index", "service", "consumer", "serializer",
    "dockerfile", "docker-compose",
)
_CODE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".kt")


def pick_key_files(tree: list[str], limit: int = 4) -> list[str]:
    """파일 트리에서 프로젝트 구조를 가장 잘 드러내는 소스 파일을 선별. (순수 함수)"""
    scored = []
    for path in tree:
        base = path.rsplit("/", 1)[-1].lower()
        is_code = path.lower().endswith(_CODE_EXT) or "dockerfile" in base or "docker-compose" in base
        if is_code and any(h in base for h in _KEY_FILE_HINTS):
            scored.append((path.count("/"), len(path), path))   # 루트에 가깝고 짧은 경로 우선
    scored.sort()
    return [p for _, _, p in scored[:limit]]


def fetch_code_snippets(url: str, limit: int = 4, max_chars: int = 1500) -> dict:
    """
    repo의 핵심 소스 파일 일부를 {경로: 내용(앞부분)}으로 반환한다.
    루트 README도 함께 포함한다 (키: "__readme__").
    ★ 예외 안전 — 어떤 실패든 빈 dict 반환 (질문 생성을 막지 않는다).
    """
    try:
        owner, repo = parse_repo_url(url)
        base = f"/repos/{owner}/{repo}"
        branch = _check(_get(base)).json().get("default_branch", "main")
        tree = _check(
            _get(f"{base}/git/trees/{branch}", params={"recursive": "1"})
        ).json()
        blobs = [t for t in tree.get("tree", []) if t.get("type") == "blob"]
        paths = [t["path"] for t in blobs]

        snippets = {}

        # 루트 README 수집
        for t in blobs:
            if is_readme_file(t["path"]):
                raw = fetch_file(owner, repo, t["path"])
                processed = preprocess_readme(raw) if raw else ""
                if processed:
                    snippets["__readme__"] = processed
                break

        for path in pick_key_files(paths, limit):
            content = fetch_file(owner, repo, path)
            if content:
                snippets[path] = content[:max_chars]
        return snippets
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════
# 면접 컨텍스트 추출 — README + LLM으로 면접 관련 정보 구조화
# ══════════════════════════════════════════════════════════════

_README_CLEANUP_PATTERNS = [
    re.compile(r"!\[.*?\]\(.*?\)"),                              # 마크다운 이미지
    re.compile(r"https?://[^\s]*shields\.io[^\s]*"),             # shields.io 배지 URL
]

_SKIP_SECTION_HEADERS = re.compile(
    r"^#{1,3}\s*(license|contributing|installation|install|getting started|setup|usage|how to run)",
    re.IGNORECASE,
)

_INSTALL_COMMANDS = re.compile(
    r"npm\s+install|pip\s+install|docker|git\s+clone",
    re.IGNORECASE,
)


def _deep_clean_readme(text: str, max_chars: int = 8000) -> str:
    """
    preprocess_readme가 처리하지 않는 패턴을 추가로 제거하고,
    ## License / ## Contributing / ## Installation 섹션 이하를 잘라낸다.
    최종 결과를 max_chars자로 제한한다.
    """
    # 마크다운 이미지·배지 URL 제거
    for pat in _README_CLEANUP_PATTERNS:
        text = pat.sub("", text)

    # 설치 명령어가 포함된 코드블록 제거
    lines = text.splitlines()
    result: list[str] = []
    skip_section = False
    in_code_block = False
    code_block_lines: list[str] = []

    for line in lines:
        # 코드블록 토글
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_lines = []
            else:
                # 코드블록 종료 — 설치 명령어 없는 경우만 포함
                in_code_block = False
                block_text = "\n".join(code_block_lines)
                if not _INSTALL_COMMANDS.search(block_text):
                    result.append(block_text)
            continue
        if in_code_block:
            code_block_lines.append(line)
            continue

        # 스킵 섹션 감지 (## License 등)
        if re.match(r"^#{1,3}\s+", line) and _SKIP_SECTION_HEADERS.match(line):
            skip_section = True
            continue
        # 같은 레벨의 새 섹션이 나오면 스킵 해제
        if skip_section and re.match(r"^#{1,3}\s+", line) and not _SKIP_SECTION_HEADERS.match(line):
            skip_section = False

        if not skip_section:
            result.append(line)

    cleaned = "\n".join(result).strip()
    return cleaned[:max_chars]


def extract_interview_context(repo_url: str) -> dict:
    """
    GitHub 레포 URL을 받아 면접 질문 생성에 필요한 구조화된 정보를 추출한다.
    analyze_repo()와 preprocess_readme()를 활용하고,
    LLM으로 면접 관련 정보만 선별해서 반환한다.
    절대 예외를 외부로 전파하지 않는다.

    반환:
        성공: {
            "ok": True,
            "data": {
                "project_name": str | None,
                "project_overview": str | None,
                "tech_stack": list[str],
                "my_role": str | None,
                "key_features": list[str],
                "technical_challenges": list[str],
                "architecture": str | None,
                "interview_points": list[str]
            }
        }
        실패: {"ok": False, "error_code": str}
    """
    from .utils import get_client, clean_json

    # 1) repo 분석
    try:
        repo_result = analyze_repo(repo_url)
    except Exception as e:
        logger.warning("[extract_interview_context] analyze_repo 예외: %s", e)
        return {"ok": False, "error_code": "GITHUB_FETCH_FAILED"}

    if not repo_result.get("ok"):
        logger.warning("[extract_interview_context] analyze_repo 실패: %s", repo_result.get("error"))
        return {"ok": False, "error_code": "GITHUB_FETCH_FAILED"}

    # 2) README 확인
    raw_readme = repo_result.get("readme", "") or ""
    if len(raw_readme) < 100:
        logger.warning("[extract_interview_context] README 없거나 너무 짧음 (%d자)", len(raw_readme))
        return {"ok": False, "error_code": "GITHUB_README_NOT_FOUND"}

    # 3) README 노이즈 제거
    cleaned_readme = preprocess_readme(raw_readme)
    cleaned_readme = _deep_clean_readme(cleaned_readme, max_chars=8000)

    # 4) LLM으로 면접 컨텍스트 추출
    client = get_client()
    prompt_content = build_interview_context_prompt(cleaned_readme)

    def _call_llm():
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt_content}],
        )
        return resp.choices[0].message.content

    # JSON 파싱 실패 시 1회 재시도
    try:
        raw = _call_llm()
        data = json.loads(clean_json(raw))
    except (json.JSONDecodeError, ValueError):
        try:
            raw = _call_llm()
            data = json.loads(clean_json(raw))
        except (json.JSONDecodeError, ValueError):
            logger.warning("[extract_interview_context] JSON 파싱 최종 실패")
            return {"ok": False, "error_code": "GITHUB_PARSE_FAILED"}
    except Exception as e:
        logger.warning("[extract_interview_context] LLM 호출 예외: %s", e)
        return {"ok": False, "error_code": "GITHUB_FETCH_FAILED"}

    # 5) analyze_repo tech_stack과 합집합 병합
    repo_frameworks: list[str] = repo_result.get("frameworks", [])
    llm_tech: list[str] = data.get("tech_stack") or []
    merged_tech = sorted(set(repo_frameworks) | set(llm_tech))
    data["tech_stack"] = merged_tech

    # 6) 성공 반환
    return {
        "ok": True,
        "data": {
            "project_name":          data.get("project_name"),
            "project_overview":      data.get("project_overview"),
            "tech_stack":            data.get("tech_stack", []),
            "my_role":               data.get("my_role"),
            "key_features":          data.get("key_features") or [],
            "technical_challenges":  data.get("technical_challenges") or [],
            "architecture":          data.get("architecture"),
            "interview_points":      data.get("interview_points") or [],
        },
    }
