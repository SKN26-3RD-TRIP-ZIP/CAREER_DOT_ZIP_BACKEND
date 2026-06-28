"""
채용공고 공급자(Provider) 추상 인터페이스.

사람인 API 승인 전에는 MockJobsService 를 사용하고,
승인 후에는 동일 인터페이스를 구현한 SaraminService 로 '서비스 레이어만 교체'하면 된다.
View 는 이 추상 인터페이스에만 의존하므로 교체 시 View/URL 변경이 필요 없다.

교체 방법(예):
    # settings.py 또는 환경변수 JOBS_PROVIDER 로 주입
    JOBS_PROVIDER = "mock"   # -> MockJobsService
    JOBS_PROVIDER = "saramin"  # -> SaraminService (승인 후 추가 구현)
"""
from abc import ABC, abstractmethod


class JobProvider(ABC):
    """채용공고 데이터 공급자 인터페이스."""

    #: 응답 source 표기 (Mock 여부를 프론트/응답에서 식별)
    source = "UNKNOWN"

    @abstractmethod
    def list_jobs(self, *, filters: dict, sort: str, page: int, size: int) -> dict:
        """
        조건에 맞는 채용공고 목록을 페이징하여 반환한다.

        Returns:
            {
                "source": "MOCK",
                "total": <int>,
                "page": <int>,
                "size": <int>,
                "results": [ <job dict>, ... ],
            }
        """
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_id: str) -> dict | None:
        """단일 채용공고 상세를 반환한다. 없으면 None."""
        raise NotImplementedError


def get_job_provider(provider_name: str | None = None) -> JobProvider:
    """
    설정에 따라 적절한 JobProvider 구현체를 반환하는 팩토리.

    provider_name 미지정 시 settings.JOBS_PROVIDER(기본 'mock')를 사용한다.
    사람인 승인 후에는 여기 'saramin' 분기에 SaraminService 를 연결한다.
    """
    name = (provider_name or "").strip().lower()
    if not name:
        try:
            from django.conf import settings

            name = getattr(settings, "JOBS_PROVIDER", "mock")
        except Exception:  # noqa: BLE001 - Django 미로딩 환경(단독 테스트) 대비
            name = "mock"
    name = str(name).strip().lower()

    if name == "mock":
        from .mock_jobs_service import MockJobsService

        return MockJobsService()

    # 사람인 승인 후 아래 분기 활성화 (동일 인터페이스 구현체로 교체)
    # if name == "saramin":
    #     from .saramin_service import SaraminService
    #     return SaraminService()

    raise ValueError(f"Unknown JOBS_PROVIDER: {name!r}")
