"""
사람인 API 미승인 대응 Mock 채용공고 서비스.

- 데이터 출처: apps/external/data/mock_jobs.json (직접 작성한 가상 데이터, source='MOCK').
- 크롤링/외부 무단 수집 없음.
- 순수 파이썬(Django 의존 없음)으로 단독 테스트 가능.
- 사람인 승인 시 동일 인터페이스(JobProvider)의 SaraminService 로 교체.
"""
import json
import threading
from pathlib import Path

from .job_provider import JobProvider

# apps/external/data/mock_jobs.json
_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mock_jobs.json"

# 허용 정렬 키 (화이트리스트)
SORT_CHOICES = {
    "latest",          # 등록 최신순 (posted_at desc)
    "oldest",          # 등록 오래된순 (posted_at asc)
    "deadline",        # 마감 임박순 (deadline asc)
    "deadline_desc",   # 마감 늦은순 (deadline desc)
    "company",         # 회사명 가나다순
}


class MockJobsService(JobProvider):
    """JSON 파일 기반 Mock 채용공고 공급자."""

    source = "MOCK"

    _cache = None
    _lock = threading.Lock()

    # ---- 데이터 로딩 (프로세스 단위 캐시) ----
    @classmethod
    def _load_all(cls) -> list[dict]:
        if cls._cache is None:
            with cls._lock:
                if cls._cache is None:
                    with open(_DATA_FILE, encoding="utf-8") as fp:
                        payload = json.load(fp)
                    cls._cache = list(payload.get("jobs", []))
        return cls._cache

    @classmethod
    def reload(cls) -> None:
        """데이터 파일을 강제로 다시 읽는다(테스트/운영 점검용)."""
        with cls._lock:
            cls._cache = None
        cls._load_all()

    # ---- public API ----
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

    # ---- 내부: 필터/정렬 ----
    @staticmethod
    def _apply_filters(jobs: list[dict], filters: dict) -> list[dict]:
        q = (filters.get("q") or "").strip().lower()
        company = (filters.get("company") or "").strip().lower()
        position = (filters.get("position") or "").strip().lower()
        tech = (filters.get("tech") or "").strip().lower()
        region = (filters.get("region") or "").strip()
        career_type = (filters.get("career_type") or "").strip()
        employment_type = (filters.get("employment_type") or "").strip()

        def tech_list(job):
            return [str(t).lower() for t in job.get("tech_stack", [])]

        result = []
        for job in jobs:
            if company and company not in str(job.get("company_name", "")).lower():
                continue
            if position and position not in str(job.get("position", "")).lower():
                continue
            if tech and not any(tech in t for t in tech_list(job)):
                continue
            if region and region != str(job.get("location", "")):
                continue
            if career_type and career_type != str(job.get("career_type", "")):
                continue
            if employment_type and employment_type != str(job.get("employment_type", "")):
                continue
            if q:
                haystack = " ".join([
                    str(job.get("company_name", "")),
                    str(job.get("position", "")),
                    str(job.get("job_description", "")),
                    " ".join(str(t) for t in job.get("tech_stack", [])),
                ]).lower()
                if q not in haystack:
                    continue
            result.append(job)
        return result

    @staticmethod
    def _apply_sort(jobs: list[dict], sort: str) -> list[dict]:
        sort = (sort or "latest").strip().lower()
        if sort not in SORT_CHOICES:
            sort = "latest"

        if sort == "latest":
            return sorted(jobs, key=lambda j: j.get("posted_at", ""), reverse=True)
        if sort == "oldest":
            return sorted(jobs, key=lambda j: j.get("posted_at", ""))
        if sort == "deadline":
            return sorted(jobs, key=lambda j: j.get("deadline", "9999-12-31"))
        if sort == "deadline_desc":
            return sorted(jobs, key=lambda j: j.get("deadline", ""), reverse=True)
        if sort == "company":
            return sorted(jobs, key=lambda j: j.get("company_name", ""))
        return jobs
