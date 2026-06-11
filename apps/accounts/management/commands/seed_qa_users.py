"""
QA 용 사용자/관리자/페르소나 계정 seed 커맨드.

실제 E2E QA 를 위해 verified 처리된 계정을 일괄 생성한다.
- 일반 QA 계정: is_verified=True, status=active, role=user
- 관리자 계정:   is_verified=True, status=active, role=admin, is_staff=True

보안:
- 비밀번호는 코드에 하드코딩하지 않는다.
- 비밀번호 출처 우선순위: --password 옵션 > 환경변수 QA_SEED_PASSWORD > 대화형 입력(getpass).
- 실제 비밀번호는 로그/문서에 남기지 않는다.

사용:
    python manage.py seed_qa_users
    QA_SEED_PASSWORD=*** python manage.py seed_qa_users
    python manage.py seed_qa_users --password ***   # CI 외 로컬 권장 X
"""
import os
from getpass import getpass

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User

# (email, name, role) — 비밀번호는 코드에 두지 않는다.
QA_ADMIN = ("tripdotzip@gmail.com", "Career.zip Admin", "admin")
QA_USERS = [
    ("parksoyun9084@gmail.com", "박소윤", "user"),
    ("jykim4169@gmail.com", "김지윤", "user"),
    ("h2yoon423@gmail.com", "홍지윤", "user"),
    ("careerzip.qa.kimhamzzi@gmail.com", "김햄찌", "user"),
    ("careerzip.qa.hongizzi@gmail.com", "홍이찌", "user"),
    ("careerzip.qa.parkjwi@gmail.com", "박쮜", "user"),
    ("careerzip.qa.parkilzzi@gmail.com", "박일찌", "user"),
]


class Command(BaseCommand):
    help = "실제 E2E QA용 verified 계정(팀원/페르소나/관리자)을 seed 한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            dest="password",
            default=None,
            help="QA 계정 공통 비밀번호. 미지정 시 QA_SEED_PASSWORD env 또는 대화형 입력 사용.",
        )

    def _resolve_password(self, opt_password):
        if opt_password:
            return opt_password
        env_pw = os.getenv("QA_SEED_PASSWORD")
        if env_pw:
            return env_pw
        # 대화형 입력(터미널). 화면/로그에 노출되지 않음.
        return getpass("QA seed 계정 비밀번호 입력: ")

    @transaction.atomic
    def handle(self, *args, **options):
        password = self._resolve_password(options.get("password"))
        if not password or len(password) < 8:
            self.stderr.write(self.style.ERROR(
                "비밀번호가 비어있거나 8자 미만입니다. (QA_SEED_PASSWORD 또는 --password)"
            ))
            return

        created, updated = 0, 0

        def upsert(email, name, role):
            nonlocal created, updated
            is_admin = role == "admin"
            user, is_new = User.objects.get_or_create(
                email=email,
                defaults={"name": name},
            )
            user.name = name
            user.is_verified = True
            user.status = "active"
            user.is_active = True
            user.role = role
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.set_password(password)
            user.save()
            if is_new:
                created += 1
            else:
                updated += 1
            # 비밀번호는 출력하지 않는다.
            self.stdout.write(f"  {'admin' if is_admin else 'user '} | {email} ({name})")

        self.stdout.write("QA seed 계정 처리 중...")
        upsert(*QA_ADMIN)
        for email, name, role in QA_USERS:
            upsert(email, name, role)

        self.stdout.write(self.style.SUCCESS(
            f"완료: 생성 {created}건, 갱신 {updated}건. (모두 is_verified=True, active)"
        ))
        self.stdout.write(
            "참고: 비밀번호는 출력/문서에 남기지 않습니다. 로그인 시 설정한 비밀번호를 사용하세요."
        )
