"""
python manage.py seed_analysis_test_data --apply

JD 분석 흐름 전체를 테스트하기 위한 시드 데이터를 생성합니다.
- 테스트 유저 (Python 백엔드 2년차 경력직)
- JD (Python/Django/Redis/Kubernetes 요구)
- 이력서 (Python/Django/Redis 보유, Kubernetes 미보유)
- 자소서 (2개 문항)
- 유저 프로필

실행 후 출력되는 jd_id / resume_id / cover_letter_id 를 분석 API에 그대로 사용할 수 있습니다.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.input.models import (
    CoverLetter,
    CoverLetterItem,
    JobDescription,
    ResumeMaster,
    UserProfile,
)

TEST_EMAIL = "test.python.dev@career.zip"
TEST_PASSWORD = "test1234!"


class Command(BaseCommand):
    help = "Seed analysis test data (Python backend dev persona)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write to the database. Default is dry-run.",
        )
        parser.add_argument(
            "--email",
            default=TEST_EMAIL,
            help="Test user email.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        email = options["email"]

        if not apply:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN: 아래 데이터가 생성될 예정입니다. 실제 적용하려면 --apply 를 붙이세요.\n"
            ))
            self._print_preview(email)
            return

        with transaction.atomic():
            result = self._seed(email)

        self.stdout.write(self.style.SUCCESS("\n분석용 테스트 데이터 생성 완료!\n"))
        self.stdout.write(f"  email          : {email}")
        self.stdout.write(f"  password       : {TEST_PASSWORD}")
        self.stdout.write(f"  user_id        : {result['user_id']}")
        self.stdout.write(f"  jd_id          : {result['jd_id']}")
        self.stdout.write(f"  resume_id      : {result['resume_id']}")
        self.stdout.write(f"  cover_letter_id: {result['cover_letter_id']}")
        self.stdout.write(self.style.SUCCESS(
            "\n분석 API 호출 예시:"
        ))
        self.stdout.write(
            f"  POST /api/v1/analysis/analyze/\n"
            f"  {{\n"
            f"    \"jd_id\": \"{result['jd_id']}\",\n"
            f"    \"resume_id\": \"{result['resume_id']}\",\n"
            f"    \"cover_letter_id\": \"{result['cover_letter_id']}\",\n"
            f"    \"career_level\": \"experienced\"\n"
            f"  }}"
        )

    def _seed(self, email):
        User = get_user_model()

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": "김파이썬",
                "is_verified": True,
                "status": "active",
                "role": "user",
                "is_active": True,
            },
        )
        if created or not user.has_usable_password():
            user.set_password(TEST_PASSWORD)
            user.save(update_fields=["password"])
        action = "생성" if created else "재사용"
        self.stdout.write(f"  user ({action}): {email}")

        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "career_type": "경력",
                "major_type": "전공",
                "desired_job": "백엔드 개발자",
                "career_year": 2,
                "github_url": "https://github.com/kim-python",
            },
        )
        self.stdout.write(f"  profile ({'생성' if created else '재사용'}): career=경력 2년, job=백엔드")

        jd, created = JobDescription.objects.get_or_create(
            user=user,
            company_name="테크스타트업",
            position="Python 백엔드 개발자",
            defaults={
                "original_text": self._jd_text(),
                "input_method": "TEXT",
                "analysis_status": "PENDING",
            },
        )
        self.stdout.write(f"  JD ({'생성' if created else '재사용'}): 테크스타트업 / Python 백엔드 개발자")

        resume, created = ResumeMaster.objects.get_or_create(
            user=user,
            email=email,
            name="김파이썬 이력서",
            defaults={
                "phone": "010-1234-5678",
                "github_url": "https://github.com/kim-python",
                "original_text": self._resume_text(),
                "is_active": True,
            },
        )
        self.stdout.write(f"  resume ({'생성' if created else '재사용'}): {resume.name}")

        cover_letter, created = CoverLetter.objects.get_or_create(
            user=user,
            jd=jd,
            title="테크스타트업 백엔드 개발자 자기소개서",
            defaults={
                "company_name": "테크스타트업",
                "is_active": True,
            },
        )
        self.stdout.write(f"  cover_letter ({'생성' if created else '재사용'}): {cover_letter.title}")

        for item in self._cover_letter_items():
            CoverLetterItem.objects.get_or_create(
                cover_letter=cover_letter,
                order_index=item["order_index"],
                defaults={
                    "question": item["question"],
                    "answer_text": item["answer_text"],
                    "max_length": item["max_length"],
                },
            )

        return {
            "user_id": user.id,
            "jd_id": str(jd.id),
            "resume_id": str(resume.id),
            "cover_letter_id": str(cover_letter.id),
        }

    def _print_preview(self, email):
        self.stdout.write("생성 예정 데이터:")
        self.stdout.write(f"  user    : {email} / 이름=김파이썬 / is_verified=True")
        self.stdout.write(f"  profile : 경력직 2년 / 전공자 / 백엔드 개발자")
        self.stdout.write(f"  JD      : 테크스타트업 / Python 백엔드 개발자")
        self.stdout.write(f"            요구: Python, Django, Redis, Kubernetes, Kafka")
        self.stdout.write(f"            우대: Kubernetes, Kafka (→ 갭 발생 시나리오)")
        self.stdout.write(f"  resume  : Python/Django/Redis 보유, Kubernetes/Kafka 없음")
        self.stdout.write(f"            경력 2년 (요구 3년 미충족 시나리오)")
        self.stdout.write(f"  자소서  : 2문항 (지원동기, 프로젝트 경험)")

    @staticmethod
    def _jd_text():
        return (
            "안녕하세요, 테크스타트업입니다.\n\n"
            "[포지션]\n"
            "Python 백엔드 개발자 (경력 3년 이상)\n\n"
            "[주요 업무]\n"
            "- Django/DRF 기반 REST API 설계 및 개발\n"
            "- Redis를 활용한 캐싱 전략 수립 및 성능 최적화\n"
            "- Kubernetes 클러스터 위에서 서비스 배포 및 운영\n"
            "- Kafka를 통한 이벤트 기반 비동기 처리 파이프라인 구축\n"
            "- PostgreSQL 쿼리 최적화 및 인덱스 설계\n\n"
            "[자격 요건]\n"
            "- Python, Django 실무 경험 3년 이상\n"
            "- Redis 캐싱 실무 적용 경험\n"
            "- REST API 설계 원칙 이해 및 실무 경험\n"
            "- 대졸 이상\n\n"
            "[우대 사항]\n"
            "- Kubernetes 컨테이너 오케스트레이션 실무 경험\n"
            "- Kafka 메시지 큐 실무 경험\n"
            "- 주도적으로 문제를 발견하고 개선안을 제안한 경험\n"
            "- 코드 리뷰 문화 정착 경험\n\n"
            "[기술 스택]\n"
            "Python, Django, DRF, Redis, Kubernetes, Kafka, PostgreSQL, Docker, GitHub Actions"
        )

    @staticmethod
    def _resume_text():
        return (
            "김파이썬 | Python 백엔드 개발자\n"
            "이메일: test.python.dev@career.zip | GitHub: github.com/kim-python\n\n"
            "[경력]\n"
            "2024.03 ~ 현재 (주)배달플랫폼 | 백엔드 개발자\n"
            "- Django/DRF 기반 주문·정산 API 개발 및 유지보수\n"
            "- Redis 캐싱 전략 도입으로 API 응답 속도 40% 개선\n"
            "- PostgreSQL 쿼리 최적화로 DB 조회 속도 30% 향상\n"
            "- GitHub Actions 기반 CI/CD 파이프라인 구축\n"
            "- 팀 코드 리뷰 프로세스 도입 주도 (PR 리뷰 정착)\n\n"
            "2022.07 ~ 2024.02 (주)이커머스솔루션 | 주니어 백엔드 개발자\n"
            "- Django REST Framework로 상품·재고 관리 API 개발\n"
            "- 기존 MySQL에서 PostgreSQL 마이그레이션 참여\n"
            "- Docker 기반 로컬 개발 환경 표준화\n\n"
            "[기술 스택]\n"
            "언어: Python\n"
            "프레임워크: Django, Django REST Framework\n"
            "데이터베이스: PostgreSQL, Redis\n"
            "인프라: Docker, GitHub Actions\n"
            "도구: Git, Jira, Confluence\n\n"
            "[학력]\n"
            "OO대학교 컴퓨터공학과 졸업 (2022.02)\n\n"
            "[프로젝트]\n"
            "배달 플랫폼 주문 API\n"
            "- Django/DRF, Redis, PostgreSQL\n"
            "- Redis TTL 전략으로 반복 조회 캐싱, 응답 속도 40% 개선\n"
            "- 주문 상태 FSM 설계 및 정산 배치 API 구현\n\n"
            "이커머스 재고 관리 시스템\n"
            "- Django, PostgreSQL, Docker\n"
            "- 동시성 이슈 대응을 위한 낙관적 락 적용\n"
            "- 상품 검색 인덱스 설계로 조회 속도 30% 향상"
        )

    @staticmethod
    def _cover_letter_items():
        return [
            {
                "order_index": 1,
                "question": "지원 동기와 입사 후 이루고 싶은 목표를 말씀해주세요.",
                "answer_text": (
                    "배달 플랫폼에서 주문·정산 API를 개발하며 대용량 트래픽 환경에서의 성능 최적화에 "
                    "깊은 관심을 갖게 되었습니다. 테크스타트업이 추구하는 이벤트 기반 아키텍처와 "
                    "Kubernetes 기반 MSA 전환 로드맵에 공감하며, 이 환경에서 실무 역량을 넓히고 싶습니다.\n\n"
                    "입사 후에는 기존 Django 서비스의 병목을 분석하고 Redis 캐싱 전략을 고도화하는 데 "
                    "기여하겠습니다. 중기적으로는 Kubernetes 운영 경험을 쌓아 배포 자동화와 장애 대응 "
                    "체계를 함께 만들어가고 싶습니다."
                ),
                "max_length": 1000,
            },
            {
                "order_index": 2,
                "question": "본인이 주도적으로 문제를 발견하고 개선한 경험을 구체적으로 설명해주세요.",
                "answer_text": (
                    "배달 플랫폼 재직 중 배달 상태 조회 API의 응답 시간이 피크 타임에 평균 800ms까지 "
                    "치솟는 문제를 발견했습니다. 팀에서 인지하지 못하고 있던 상황에서 제가 먼저 "
                    "쿼리 실행 계획을 분석해 N+1 문제와 불필요한 JOIN을 확인했습니다.\n\n"
                    "해결을 위해 Redis TTL 기반 캐싱 레이어를 도입하고 쿼리를 리팩토링했습니다. "
                    "배포 후 응답 시간이 평균 120ms로 85% 감소했고, 서버 부하도 30% 줄었습니다. "
                    "이 경험을 팀 위키에 정리해 코드 리뷰 체크리스트로 채택되었습니다."
                ),
                "max_length": 1000,
            },
        ]
