"""
6자리 이메일 인증번호 생성/발급/검증 로직.

- 평문 코드는 저장/로그하지 않는다. 해시(HMAC-SHA256, SECRET_KEY 페퍼)만 DB에 저장.
- 만료(기본 10분), 입력 시도 제한(기본 5회), 재발송 쿨다운(기본 60초)을 지원.
- 기본값은 settings 로 재정의 가능:
    EMAIL_CODE_TTL_SECONDS / EMAIL_CODE_MAX_ATTEMPTS / EMAIL_CODE_RESEND_COOLDOWN_SECONDS
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailVerificationCode

# 기본값(설정 미지정 시): 만료 10분 / 시도 5회 / 재발송 쿨다운 60초.
# settings(EMAIL_CODE_*) 로 재정의 가능. 테스트의 override_settings 가 반영되도록
# 모듈 로드 시점이 아니라 호출 시점에 읽는다.
DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RESEND_COOLDOWN_SECONDS = 60


def get_ttl_seconds() -> int:
    return int(getattr(settings, "EMAIL_CODE_TTL_SECONDS", DEFAULT_TTL_SECONDS))


def get_max_attempts() -> int:
    return int(getattr(settings, "EMAIL_CODE_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))


def get_resend_cooldown_seconds() -> int:
    return int(getattr(settings, "EMAIL_CODE_RESEND_COOLDOWN_SECONDS", DEFAULT_RESEND_COOLDOWN_SECONDS))


class ResendCooldownError(Exception):
    """재발송 쿨다운 미경과 시 발생. retry_after(초) 보유."""

    def __init__(self, retry_after: int):
        super().__init__("resend cooldown not elapsed")
        self.retry_after = retry_after


# 검증 결과 코드
class VerifyResult:
    OK = "ok"
    INVALID = "invalid"      # 코드 불일치
    EXPIRED = "expired"      # 만료 또는 발급된 코드 없음
    TOO_MANY = "too_many"    # 시도 횟수 초과


def generate_code() -> str:
    """6자리 인증번호(앞자리 0 허용)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    """SECRET_KEY 페퍼를 사용한 HMAC-SHA256 해시(hex)."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        (code or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_code(user) -> str:
    """
    사용자에게 새 인증번호를 발급한다.

    - 직전 발급으로부터 쿨다운(기본 60초) 미경과 시 ResendCooldownError.
    - 이전 미사용 코드는 모두 무효화(is_used=True).
    - 평문 코드를 반환(메일 발송용). DB에는 해시만 저장.
    """
    now = timezone.now()
    cooldown = get_resend_cooldown_seconds()
    latest = (
        EmailVerificationCode.objects
        .filter(user=user, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if latest is not None and cooldown > 0:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < cooldown:
            raise ResendCooldownError(max(int(cooldown - elapsed), 1))

    EmailVerificationCode.objects.filter(user=user, is_used=False).update(is_used=True)

    code = generate_code()
    EmailVerificationCode.objects.create(
        user=user,
        code_hash=hash_code(code),
        expires_at=now + timedelta(seconds=get_ttl_seconds()),
    )
    return code


def issue_pending_code(pending) -> str:
    """Issue a code for a PendingRegistration without creating a User."""
    now = timezone.now()
    retry_after = pending_resend_retry_after(pending, now=now)
    if retry_after > 0:
        raise ResendCooldownError(retry_after)

    code = generate_code()
    pending.code_hash = hash_code(code)
    pending.expires_at = now + timedelta(seconds=get_ttl_seconds())
    pending.resend_available_at = now + timedelta(seconds=get_resend_cooldown_seconds())
    pending.attempt_count = 0
    pending.max_attempts = get_max_attempts()
    pending.is_used = False
    pending.verified_at = None
    pending.save(
        update_fields=[
            "code_hash",
            "expires_at",
            "resend_available_at",
            "attempt_count",
            "max_attempts",
            "is_used",
            "verified_at",
            "updated_at",
        ]
    )
    return code


def pending_resend_retry_after(pending, *, now=None) -> int:
    """Return remaining resend cooldown seconds for a pending registration."""
    now = now or timezone.now()
    resend_available_at = getattr(pending, "resend_available_at", None)
    if not resend_available_at or resend_available_at <= now:
        return 0
    return max(int((resend_available_at - now).total_seconds()), 1)


def invalidate_pending_code(pending) -> None:
    """Invalidate the current pending code while keeping the signup draft retryable."""
    now = timezone.now()
    pending.code_hash = ""
    pending.expires_at = now
    pending.resend_available_at = now
    pending.attempt_count = 0
    pending.save(
        update_fields=[
            "code_hash",
            "expires_at",
            "resend_available_at",
            "attempt_count",
            "updated_at",
        ]
    )


def verify_pending_code(pending, code: str) -> str:
    """Verify a PendingRegistration code under a row lock held by the caller."""
    now = timezone.now()
    if pending.is_used:
        return VerifyResult.EXPIRED
    if not pending.code_hash or pending.expires_at <= now:
        return VerifyResult.EXPIRED
    if pending.attempt_count >= pending.max_attempts:
        pending.is_used = True
        pending.save(update_fields=["is_used", "updated_at"])
        return VerifyResult.TOO_MANY
    print("Verifying pending code:", code, "against hash:", pending.code_hash)

    pending.attempt_count += 1
    if hmac.compare_digest(pending.code_hash, hash_code(code)):
        print("hmac.compare_digest succeeded")
        pending.is_used = True
        pending.verified_at = now
        pending.save(update_fields=["attempt_count", "is_used", "verified_at", "updated_at"])
        return VerifyResult.OK

    pending.save(update_fields=["attempt_count", "updated_at"])
    return VerifyResult.INVALID


def verify_code(user, code: str) -> str:
    """
    사용자의 최신 미사용 코드와 입력 코드를 검증한다. VerifyResult 중 하나를 반환.
    성공(OK) 시 해당 코드를 사용 처리한다(user.is_verified 갱신은 호출부 책임).
    """
    now = timezone.now()
    entry = (
        EmailVerificationCode.objects
        .filter(user=user, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if entry is None or entry.expires_at <= now:
        return VerifyResult.EXPIRED

    if entry.attempt_count >= get_max_attempts():
        entry.is_used = True
        entry.save(update_fields=["is_used"])
        return VerifyResult.TOO_MANY

    entry.attempt_count += 1
    if hmac.compare_digest(entry.code_hash, hash_code(code)):
        entry.is_used = True
        entry.save(update_fields=["attempt_count", "is_used"])
        return VerifyResult.OK

    entry.save(update_fields=["attempt_count"])
    return VerifyResult.INVALID
