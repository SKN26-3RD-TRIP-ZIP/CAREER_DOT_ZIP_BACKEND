import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.input.models import (
    CoverLetter,
    CoverLetterItem,
    JobDescription,
    ProjectExperience,
    ResumeMaster,
    UserProfile,
)


HAMZZI_EMAIL = "hamzzi.kim@example.com"
TECH_STACKS = ["Java", "Spring Boot", "MySQL", "JPA", "Redis", "Docker"]


class Command(BaseCommand):
    help = "Seed a minimal idempotent MVP sample dataset for end-to-end local flow checks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually create missing sample rows. Default is dry-run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview planned changes without modifying the database. This is the default.",
        )
        parser.add_argument(
            "--email",
            default=HAMZZI_EMAIL,
            help="Sample user email to reuse or create.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        email = options["email"]

        plan = self._build_plan(email)
        self._print_plan(plan, apply)

        if not apply:
            self.stdout.write(self.style.WARNING("DRY-RUN: no database changes were made."))
            return

        with transaction.atomic():
            result = self._apply_plan(email)

        self.stdout.write(self.style.SUCCESS("MVP sample dataset is ready."))
        self._print_result(result)

    def _build_plan(self, email):
        User = get_user_model()
        user = User.objects.filter(email=email).first()
        profile = UserProfile.objects.filter(user=user).first() if user else None
        jd = self._find_jd(user) if user else None
        resume = self._find_resume(user, email) if user else None
        cover_letter = self._find_cover_letter(user, jd) if user and jd else None
        projects = list(ProjectExperience.objects.filter(
            user=user,
            project_name__in=[project["project_name"] for project in self._project_payloads()],
        ).order_by("project_name")) if user else []

        return {
            "user": user,
            "profile": profile,
            "jd": jd,
            "resume": resume,
            "cover_letter": cover_letter,
            "project_count": len(projects),
            "project_names": [project.project_name for project in projects],
            "missing": {
                "user": user is None,
                "profile": user is not None and profile is None,
                "jd": user is not None and jd is None,
                "resume": user is not None and resume is None,
                "cover_letter": user is not None and jd is not None and cover_letter is None,
                "projects": max(0, 2 - len(projects)),
            },
        }

    def _apply_plan(self, email):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "name": "김햄찌",
                "is_verified": True,
                "status": "active",
                "role": "user",
                "is_active": True,
            },
        )
        if not user.has_usable_password():
            user.set_password("mvp-sample-password")
            user.save(update_fields=["password"])

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "career_type": "신입",
                "major_type": "비전공",
                "desired_job": "백엔드 개발자",
                "career_year": 0,
                "github_url": "https://github.com/hamzzi",
            },
        )
        jd, _ = JobDescription.objects.get_or_create(
            user=user,
            company_name="Career.zip",
            position="주니어 백엔드 개발자",
            defaults={
                "original_text": self._jd_text(),
                "input_method": "TEXT",
                "job_requirements": "Java, Spring Boot, MySQL, JPA 기반 REST API 개발 역량",
                "keywords": json.dumps(TECH_STACKS + ["REST API", "JWT"], ensure_ascii=False),
                "analysis_status": "PENDING",
            },
        )
        resume, _ = ResumeMaster.objects.get_or_create(
            user=user,
            email=email,
            name="김햄찌",
            defaults={
                "github_url": "https://github.com/hamzzi",
                "original_text": self._resume_text(),
                "extracted_keywords": json.dumps(TECH_STACKS, ensure_ascii=False),
                "is_active": True,
            },
        )
        cover_letter, _ = CoverLetter.objects.get_or_create(
            user=user,
            jd=jd,
            title="김햄찌 백엔드 개발자 지원 자기소개서",
            defaults={
                "company_name": jd.company_name,
                "is_active": True,
            },
        )
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

        projects = []
        for payload in self._project_payloads():
            project, _ = ProjectExperience.objects.get_or_create(
                user=user,
                project_name=payload["project_name"],
                defaults=payload,
            )
            projects.append(project)

        return {
            "user_id": user.id,
            "profile_id": str(profile.id),
            "jd_id": str(jd.id),
            "resume_id": str(resume.id),
            "cover_letter_id": str(cover_letter.id),
            "project_ids": [str(project.id) for project in projects],
            "session_ready": all([user.id, jd.id, resume.id, cover_letter.id]),
        }

    def _print_plan(self, plan, apply):
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"mode: {mode}")
        self.stdout.write("planned dataset:")
        self.stdout.write(f"- user: {'create' if plan['missing']['user'] else 'reuse'} {HAMZZI_EMAIL}")
        self.stdout.write(f"- profile: {'create' if plan['missing']['profile'] else 'reuse' if plan['profile'] else 'pending user'}")
        self.stdout.write(f"- jd: {'create' if plan['missing']['jd'] else 'reuse' if plan['jd'] else 'pending user'}")
        self.stdout.write(f"- resume: {'create' if plan['missing']['resume'] else 'reuse' if plan['resume'] else 'pending user'}")
        self.stdout.write(f"- cover_letter: {'create' if plan['missing']['cover_letter'] else 'reuse' if plan['cover_letter'] else 'pending jd'}")
        self.stdout.write(f"- projects: existing={plan['project_count']}, create={plan['missing']['projects']}")
        if plan["project_names"]:
            self.stdout.write(f"  existing_project_names: {', '.join(plan['project_names'])}")

    def _print_result(self, result):
        self.stdout.write(f"user_id: {result['user_id']}")
        self.stdout.write(f"jd_id: {result['jd_id']}")
        self.stdout.write(f"resume_id: {result['resume_id']}")
        self.stdout.write(f"cover_letter_id: {result['cover_letter_id']}")
        self.stdout.write(f"project_ids: {', '.join(result['project_ids'])}")
        self.stdout.write(f"session_ready: {result['session_ready']}")

    @staticmethod
    def _find_jd(user):
        return JobDescription.objects.filter(
            user=user,
            company_name="Career.zip",
            position="주니어 백엔드 개발자",
        ).first()

    @staticmethod
    def _find_resume(user, email):
        return ResumeMaster.objects.filter(user=user, email=email, name="김햄찌").first()

    @staticmethod
    def _find_cover_letter(user, jd):
        return CoverLetter.objects.filter(
            user=user,
            jd=jd,
            title="김햄찌 백엔드 개발자 지원 자기소개서",
        ).first()

    @staticmethod
    def _jd_text():
        return (
            "주니어 백엔드 개발자를 채용합니다. Java, Spring Boot, MySQL, JPA를 활용한 "
            "REST API 개발 경험과 Redis, Docker 기반 서비스 운영 경험을 우대합니다. "
            "인증/인가, 트랜잭션, 인덱스, 배포 흐름을 이해한 지원자를 찾습니다."
        )

    @staticmethod
    def _resume_text():
        return (
            "김햄찌는 영어영문학 전공 후 6개월 국비 지원 백엔드 부트캠프를 수료했습니다. "
            "Java, Spring Boot, MySQL, JPA, Redis, Docker를 활용해 REST API 프로젝트를 "
            "구현했으며 CS 기초와 데이터베이스 심화 면접을 준비하고 있습니다."
        )

    @staticmethod
    def _cover_letter_items():
        return [
            {
                "order_index": 1,
                "question": "비전공자인데 왜 백엔드 개발자가 되고 싶었나요?",
                "answer_text": (
                    "사용자 문제를 구조적으로 해결하는 과정에 흥미를 느껴 백엔드 개발을 선택했습니다. "
                    "부트캠프에서 API 설계와 데이터베이스 모델링을 경험하며 서비스의 안정성을 만드는 "
                    "역할에 매력을 느꼈습니다."
                ),
                "max_length": 700,
            },
            {
                "order_index": 2,
                "question": "가장 자신 있는 프로젝트 경험을 설명해주세요.",
                "answer_text": (
                    "Hamzzi Market API에서 상품/거래 도메인을 맡아 상태 전이, 찜 기능, Redis 캐시를 "
                    "구현했습니다. 단순 구현보다 거래 상태 기준과 예외 상황을 명확히 정리하는 데 집중했습니다."
                ),
                "max_length": 700,
            },
        ]

    @staticmethod
    def _project_payloads():
        return [
            {
                "project_name": "Hamzzi Market API",
                "description": "중고거래 상품 등록, 찜, 채팅, 거래 상태 관리를 제공하는 REST API 서버",
                "contribution": "상품/거래 도메인 API 설계 및 구현, 기여도 80%",
                "tech_stack": ["Java", "Spring Boot", "MySQL", "JPA", "Spring Security", "Redis"],
                "github_url": "https://github.com/hamzzi/hamzzi-market-api",
                "start_date": "2026.01",
                "end_date": "2026.03",
            },
            {
                "project_name": "Career Buddy Backend",
                "description": "취업 준비 일정, 지원 기업, 면접 기록을 관리하는 백엔드 API 서비스",
                "contribution": "회원 인증, JWT 로그인, 면접 기록 API 구현, 기여도 70%",
                "tech_stack": ["Java", "Spring Boot", "MySQL", "JPA", "JWT", "Docker"],
                "github_url": "https://github.com/hamzzi/career-buddy-backend",
                "start_date": "2026.04",
                "end_date": "2026.06",
            },
        ]
