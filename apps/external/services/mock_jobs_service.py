"""Deterministic synthetic job provider for development and QA.

The data produced here is fully synthetic. It does not crawl, copy, or label
Saramin or any other third-party job-board data as a source.
"""

from __future__ import annotations

import json
import random
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from django.conf import settings

from .job_provider import JobProvider

SOURCE = "CAREER_ZIP_MOCK"
DEFAULT_COUNT = 10000
DEFAULT_SEED = 2026

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GENERATED_DATA_FILE = DATA_DIR / "mock_jobs.generated.json"

SORT_CHOICES = {
    "latest",
    "-posted_at",
    "posted_at",
    "oldest",
    "deadline",
    "-deadline",
    "deadline_desc",
    "company",
    "company_name",
    "position",
}


POSITION_PROFILES = [
    {
        "position": "백엔드 개발자",
        "tech_stack": ["Python", "Django", "DRF", "MySQL", "Docker"],
        "main_tasks": ["REST API 개발", "데이터 모델링", "서비스 운영 지표 개선"],
        "requirements": ["Python 기본기", "RDB 설계 이해", "Git 협업 경험"],
        "preferred": ["Django 프로젝트 경험", "테스트 코드 작성 경험"],
        "keywords": ["backend", "api", "django", "python"],
    },
    {
        "position": "프론트엔드 개발자",
        "tech_stack": ["JavaScript", "React", "TypeScript", "Vite"],
        "main_tasks": ["React 화면 개발", "상태 관리 개선", "접근성 품질 보완"],
        "requirements": ["React 컴포넌트 설계 경험", "HTTP API 연동 경험"],
        "preferred": ["TypeScript 사용 경험", "디자인 시스템 이해"],
        "keywords": ["frontend", "react", "vite"],
    },
    {
        "position": "데이터 엔지니어",
        "tech_stack": ["Python", "Airflow", "Spark", "AWS", "SQL"],
        "main_tasks": ["데이터 파이프라인 구축", "배치 작업 모니터링", "품질 검증 자동화"],
        "requirements": ["SQL 활용 능력", "ETL 파이프라인 이해"],
        "preferred": ["Airflow 운영 경험", "클라우드 데이터 서비스 경험"],
        "keywords": ["data", "etl", "pipeline"],
    },
    {
        "position": "AI/ML 엔지니어",
        "tech_stack": ["Python", "PyTorch", "FastAPI", "Vector DB"],
        "main_tasks": ["모델 추론 API 개발", "실험 결과 분석", "모델 품질 모니터링"],
        "requirements": ["머신러닝 기초", "Python 기반 실험 경험"],
        "preferred": ["LLM 서비스 개발 경험", "MLOps 이해"],
        "keywords": ["ai", "ml", "llm", "python"],
    },
    {
        "position": "DevOps 엔지니어",
        "tech_stack": ["Linux", "Docker", "Nginx", "AWS", "GitHub Actions"],
        "main_tasks": ["배포 자동화", "운영 로그 개선", "장애 대응 프로세스 정리"],
        "requirements": ["Linux 운영 경험", "컨테이너 기본 이해"],
        "preferred": ["CI/CD 파이프라인 구축 경험", "모니터링 도구 사용 경험"],
        "keywords": ["devops", "docker", "aws", "cicd"],
    },
    {
        "position": "보안 엔지니어",
        "tech_stack": ["Python", "Linux", "OWASP", "SIEM"],
        "main_tasks": ["취약점 점검", "보안 로그 분석", "보안 가이드 작성"],
        "requirements": ["웹 보안 기본 지식", "취약점 재현과 보고서 작성 경험"],
        "preferred": ["OWASP Top 10 이해", "보안 자동화 스크립트 경험"],
        "keywords": ["security", "owasp"],
    },
]

COMPANY_PREFIXES = [
    "커리어",
    "코드",
    "모먼트",
    "넥스트",
    "브릿지",
    "루프",
    "스택",
    "그로스",
    "클라우드",
    "데브",
]
COMPANY_SUFFIXES = ["테크랩", "소프트", "데이터웍스", "플랫폼즈", "시스템즈", "인사이트"]
CAREER_TYPES = ["신입", "주니어", "경력", "인턴"]
EMPLOYMENT_TYPES = ["정규직", "계약직", "인턴", "전환형 인턴"]
LOCATIONS = ["서울", "경기", "인천", "대전", "대구", "부산", "광주", "원격"]
EDUCATION_CHOICES = ["학력 무관", "초대졸 이상", "대졸 이상"]
SALARY_RANGES = ["회사 내규", "3,000~4,000만원", "4,000~5,500만원", "5,000~7,000만원"]


def _setting_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _contains_any(haystack: Iterable[str], needles: Iterable[str]) -> bool:
    values = [str(item).lower() for item in haystack]
    terms = [str(item).lower() for item in needles if str(item).strip()]
    if not terms:
        return True
    return all(any(term in value for value in values) for term in terms)


def build_job_jd_text(job: dict) -> str:
    """Build a JD text block compatible with the existing JobDescription model."""

    lines = [
        "[출처] CAREER_ZIP_MOCK 개발·연습용 합성 공고",
        f"[회사] {job.get('company_name', '')}",
        f"[직무] {job.get('position', '')}",
        f"[경력] {job.get('career_type', '')}",
        f"[고용형태] {job.get('employment_type', '')}",
        f"[지역] {job.get('location', '')}",
        f"[기술스택] {', '.join(_as_list(job.get('tech_stack')))}",
        "[주요업무]",
        *[f"- {item}" for item in _as_list(job.get("main_tasks"))],
        "[자격요건]",
        *[f"- {item}" for item in _as_list(job.get("requirements"))],
        "[우대사항]",
        *[f"- {item}" for item in _as_list(job.get("preferred"))],
    ]
    if job.get("job_description"):
        lines.extend(["[공고요약]", str(job["job_description"])])
    return "\n".join(line for line in lines if line)


def generate_mock_jobs(*, count: int = DEFAULT_COUNT, seed: int = DEFAULT_SEED) -> list[dict]:
    """Generate stable synthetic job records."""

    count = max(int(count), 0)
    rng = random.Random(int(seed))
    posted_base = date(2026, 6, 1)
    jobs: list[dict] = []

    for index in range(1, count + 1):
        profile = POSITION_PROFILES[(index - 1) % len(POSITION_PROFILES)]
        company_name = (
            f"{COMPANY_PREFIXES[(index - 1) % len(COMPANY_PREFIXES)]}"
            f"{COMPANY_SUFFIXES[(index + seed) % len(COMPANY_SUFFIXES)]}"
        )
        career_type = CAREER_TYPES[(index + rng.randrange(len(CAREER_TYPES))) % len(CAREER_TYPES)]
        employment_type = EMPLOYMENT_TYPES[(index + rng.randrange(len(EMPLOYMENT_TYPES))) % len(EMPLOYMENT_TYPES)]
        location = LOCATIONS[(index + rng.randrange(len(LOCATIONS))) % len(LOCATIONS)]
        posted_at = posted_base + timedelta(days=(index - 1) % 30)
        deadline = posted_at + timedelta(days=30 + (index % 45))
        keywords = sorted(set(profile["keywords"] + [profile["position"], career_type, location]))

        job = {
            "job_id": f"mock-job-{index:06d}",
            "company_name": company_name,
            "position": profile["position"],
            "career_type": career_type,
            "employment_type": employment_type,
            "location": location,
            "tech_stack": list(profile["tech_stack"]),
            "main_tasks": list(profile["main_tasks"]),
            "requirements": list(profile["requirements"]),
            "preferred": list(profile["preferred"]),
            "education": EDUCATION_CHOICES[index % len(EDUCATION_CHOICES)],
            "salary_range": SALARY_RANGES[index % len(SALARY_RANGES)],
            "posted_at": posted_at.isoformat(),
            "deadline": deadline.isoformat(),
            "keywords": keywords,
            "job_description": (
                f"{company_name}의 {profile['position']} 포지션 합성 공고입니다. "
                "실제 기업 공고가 아니며 Career.zip 개발·QA 흐름 검증에만 사용합니다."
            ),
            "source": SOURCE,
            "is_mock": True,
        }
        job["jd_text"] = build_job_jd_text(job)
        jobs.append(job)

    return jobs


class MockJobsService(JobProvider):
    """Synthetic mock job provider."""

    source = SOURCE

    _cache: list[dict] | None = None
    _lock = threading.Lock()

    @classmethod
    def _configured_data_file(cls) -> Path:
        configured = getattr(settings, "MOCK_JOBS_DATA_FILE", "")
        if configured:
            return Path(configured)
        return GENERATED_DATA_FILE

    @classmethod
    def _load_all(cls) -> list[dict]:
        if cls._cache is None:
            with cls._lock:
                if cls._cache is None:
                    data_file = cls._configured_data_file()
                    if data_file.exists():
                        with open(data_file, encoding="utf-8") as fp:
                            payload = json.load(fp)
                        jobs = list(payload.get("jobs", []))
                    else:
                        jobs = generate_mock_jobs(
                            count=_setting_int("MOCK_JOBS_COUNT", DEFAULT_COUNT),
                            seed=_setting_int("MOCK_JOBS_SEED", DEFAULT_SEED),
                        )
                    cls._cache = [cls._normalize_job(job) for job in jobs]
        return cls._cache

    @classmethod
    def reload(cls) -> None:
        with cls._lock:
            cls._cache = None
        cls._load_all()

    @staticmethod
    def _normalize_job(job: dict) -> dict:
        normalized = dict(job)
        normalized["source"] = SOURCE
        normalized["is_mock"] = True
        for key in ("tech_stack", "main_tasks", "requirements", "preferred", "keywords"):
            normalized[key] = _as_list(normalized.get(key))
        if "jd_text" not in normalized:
            normalized["jd_text"] = build_job_jd_text(normalized)
        return normalized

    def list_jobs(self, *, filters: dict, sort: str = "latest", page: int = 1, size: int = 10) -> dict:
        jobs = list(self._load_all())
        jobs = self._apply_filters(jobs, filters or {})
        jobs = self._apply_sort(jobs, sort)

        total = len(jobs)
        page = max(int(page or 1), 1)
        size = min(max(int(size or 10), 1), 100)
        start = (page - 1) * size
        end = start + size

        return {
            "source": self.source,
            "is_mock": True,
            "total": total,
            "page": page,
            "size": size,
            "results": jobs[start:end],
        }

    def get_job(self, job_id: str) -> dict | None:
        if not job_id:
            return None
        target = str(job_id).strip()
        for job in self._load_all():
            if str(job.get("job_id")) == target:
                return job
        return None

    @staticmethod
    def _apply_filters(jobs: list[dict], filters: dict) -> list[dict]:
        keyword = (filters.get("keyword") or filters.get("q") or "").strip().lower()
        company = (filters.get("company") or "").strip().lower()
        position = (filters.get("position") or "").strip().lower()
        tech_terms = _as_list(filters.get("tech_stack") or filters.get("tech"))
        location = (filters.get("location") or filters.get("region") or "").strip()
        career_type = (filters.get("career_type") or "").strip()
        employment_type = (filters.get("employment_type") or "").strip()

        result = []
        for job in jobs:
            if company and company not in str(job.get("company_name", "")).lower():
                continue
            if position and position not in str(job.get("position", "")).lower():
                continue
            if tech_terms and not _contains_any(job.get("tech_stack", []), tech_terms):
                continue
            if location and location != str(job.get("location", "")):
                continue
            if career_type and career_type != str(job.get("career_type", "")):
                continue
            if employment_type and employment_type != str(job.get("employment_type", "")):
                continue
            if keyword:
                haystack = " ".join(
                    [
                        str(job.get("company_name", "")),
                        str(job.get("position", "")),
                        str(job.get("career_type", "")),
                        str(job.get("employment_type", "")),
                        str(job.get("location", "")),
                        str(job.get("job_description", "")),
                        " ".join(_as_list(job.get("tech_stack"))),
                        " ".join(_as_list(job.get("main_tasks"))),
                        " ".join(_as_list(job.get("requirements"))),
                        " ".join(_as_list(job.get("preferred"))),
                        " ".join(_as_list(job.get("keywords"))),
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            result.append(job)
        return result

    @staticmethod
    def _apply_sort(jobs: list[dict], sort: str) -> list[dict]:
        sort = (sort or "latest").strip().lower()
        if sort not in SORT_CHOICES:
            sort = "latest"

        if sort in {"latest", "-posted_at"}:
            return sorted(jobs, key=lambda job: job.get("posted_at", ""), reverse=True)
        if sort in {"oldest", "posted_at"}:
            return sorted(jobs, key=lambda job: job.get("posted_at", ""))
        if sort == "deadline":
            return sorted(jobs, key=lambda job: job.get("deadline", "9999-12-31"))
        if sort in {"deadline_desc", "-deadline"}:
            return sorted(jobs, key=lambda job: job.get("deadline", ""), reverse=True)
        if sort in {"company", "company_name"}:
            return sorted(jobs, key=lambda job: job.get("company_name", ""))
        if sort == "position":
            return sorted(jobs, key=lambda job: job.get("position", ""))
        return jobs
