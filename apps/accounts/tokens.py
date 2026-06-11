"""
이메일 인증 토큰 유틸리티.

DB 변경 없이 Django의 서명(signing) 기반 토큰을 사용한다.
- itsdangerous 스타일의 서명 토큰으로, SECRET_KEY 로 위조 검증.
- 토큰에는 민감정보(비밀번호/실제 인증코드 등)를 넣지 않는다.
- 토큰 payload: {"uid": user_id, "email": email}
  (issued_at/timestamp 는 TimestampSigner 가 내부적으로 부착하며 max_age 로 만료 검증)

ERD/DB 영향: 없음 (별도 토큰 테이블을 만들지 않음).
운영에서 1회용/폐기형 토큰이 필요하면 별도 EmailVerificationToken 테이블 + migration 이
필요하며, 그 경우 ERD 수정과 마이그레이션 생성이 선행되어야 한다 (NEEDS_CONFIRMATION).
"""
from django.conf import settings
from django.core import signing

# 이메일 인증 토큰 전용 salt (네임스페이스 분리)
EMAIL_VERIFICATION_SALT = "accounts.email-verification"

# 기본 만료: 24시간 (초)
DEFAULT_MAX_AGE_SECONDS = 60 * 60 * 24


def generate_email_verification_token(user) -> str:
    """주어진 user 에 대한 서명된 이메일 인증 토큰을 생성한다."""
    payload = {"uid": user.id, "email": user.email}
    return signing.dumps(payload, salt=EMAIL_VERIFICATION_SALT)


def verify_email_verification_token(token: str, max_age: int = None) -> dict:
    """
    토큰을 검증하고 payload(dict) 를 반환한다.

    실패 시 예외를 발생시킨다:
    - signing.SignatureExpired : 만료
    - signing.BadSignature     : 위조/손상/형식 오류
    """
    if max_age is None:
        max_age = getattr(
            settings, "EMAIL_VERIFICATION_TOKEN_MAX_AGE", DEFAULT_MAX_AGE_SECONDS
        )
    # SignatureExpired 는 BadSignature 의 하위 클래스이므로 호출부에서 구분 처리 가능
    return signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=max_age)
